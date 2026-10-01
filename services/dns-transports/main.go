package main

import (
	"bytes"
	"context"
	"crypto/tls"
	"encoding/base32"
	"encoding/binary"
	"encoding/hex"
	"errors"
	"io"
	"log"
	"net"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/miekg/dns"
	"github.com/quic-go/quic-go"
)

var b32 = base32.StdEncoding.WithPadding(base32.NoPadding)

func tokenFromName(name, suffix string) (string, error) {
	name = strings.ToLower(strings.TrimSuffix(name, "."))
	suffix = "." + strings.ToLower(strings.Trim(suffix, "."))
	if !strings.HasSuffix(name, suffix) {
		return "", errors.New("invalid name")
	}
	label := strings.TrimSuffix(name, suffix)
	if len(label) != 52 || strings.Contains(label, ".") {
		return "", errors.New("invalid name")
	}
	raw, e := b32.DecodeString(strings.ToUpper(label))
	if e != nil || len(raw) != 32 || strings.ToLower(b32.EncodeToString(raw)) != label {
		return "", errors.New("invalid name")
	}
	return hex.EncodeToString(raw), nil
}
func readWire(r io.Reader) ([]byte, error) {
	var size [2]byte
	if _, e := io.ReadFull(r, size[:]); e != nil {
		return nil, e
	}
	n := int(binary.BigEndian.Uint16(size[:]))
	if n < 12 {
		return nil, errors.New("short DNS")
	}
	b := make([]byte, n)
	_, e := io.ReadFull(r, b)
	return b, e
}
func writeWire(w io.Writer, b []byte) error {
	if len(b) > 65535 || len(b) < 12 {
		return errors.New("invalid DNS length")
	}
	f := make([]byte, len(b)+2)
	binary.BigEndian.PutUint16(f, uint16(len(b)))
	copy(f[2:], b)
	for len(f) > 0 {
		n, e := w.Write(f)
		if e != nil {
			return e
		}
		if n == 0 {
			return io.ErrShortWrite
		}
		f = f[n:]
	}
	return nil
}
func failure(q *dns.Msg, rcode int) []byte {
	r := new(dns.Msg)
	r.SetReply(q)
	r.RecursionAvailable = true
	r.Rcode = rcode
	b, _ := r.Pack()
	return b
}

type gateway struct {
	url, suffix string
	client      *http.Client
	slots       chan struct{}
	mu          sync.Mutex
	ips         map[string]int
	total       int
}

func (g *gateway) admit(a net.Addr) bool {
	ip, _, e := net.SplitHostPort(a.String())
	if e != nil {
		return false
	}
	g.mu.Lock()
	defer g.mu.Unlock()
	if g.total >= 256 || g.ips[ip] >= 32 {
		return false
	}
	g.total++
	g.ips[ip]++
	return true
}
func (g *gateway) release(a net.Addr) {
	ip, _, _ := net.SplitHostPort(a.String())
	g.mu.Lock()
	defer g.mu.Unlock()
	g.total--
	g.ips[ip]--
	if g.ips[ip] == 0 {
		delete(g.ips, ip)
	}
}
func (g *gateway) resolve(ctx context.Context, token string, b []byte, doq bool) ([]byte, error) {
	q := new(dns.Msg)
	if q.Unpack(b) != nil || q.Response || q.Opcode != 0 || len(q.Question) != 1 || doq && q.Id != 0 {
		return nil, errors.New("invalid query")
	}
	select {
	case g.slots <- struct{}{}:
		defer func() { <-g.slots }()
	default:
		return failure(q, dns.RcodeServerFailure), nil
	}
	ctx, cancel := context.WithTimeout(ctx, 13*time.Second)
	defer cancel()
	req, e := http.NewRequestWithContext(ctx, "POST", g.url+"/dns-query/"+token, bytes.NewReader(b))
	if e != nil {
		return nil, errors.New("internal request")
	}
	req.Header.Set("Content-Type", "application/dns-message")
	req.Header.Set("Accept", "application/dns-message")
	r, e := g.client.Do(req)
	if e != nil {
		return failure(q, dns.RcodeServerFailure), nil
	}
	defer r.Body.Close()
	if r.StatusCode != 200 {
		code := dns.RcodeServerFailure
		if r.StatusCode == 403 || r.StatusCode == 404 {
			code = dns.RcodeRefused
		}
		return failure(q, code), nil
	}
	out, e := io.ReadAll(io.LimitReader(r.Body, 65536))
	if e != nil || len(out) > 65535 {
		return failure(q, dns.RcodeServerFailure), nil
	}
	a := new(dns.Msg)
	if a.Unpack(out) != nil || !a.Response || a.Id != q.Id || len(a.Question) != 1 || a.Question[0] != q.Question[0] {
		return failure(q, dns.RcodeServerFailure), nil
	}
	return out, nil
}
func (g *gateway) serveTLS(ctx context.Context, l net.Listener) {
	for {
		c, e := l.Accept()
		if e != nil {
			return
		}
		if !g.admit(c.RemoteAddr()) {
			c.Close()
			continue
		}
		go func() {
			defer c.Close()
			defer g.release(c.RemoteAddr())
			t := c.(*tls.Conn)
			t.SetDeadline(time.Now().Add(5 * time.Second))
			if t.HandshakeContext(ctx) != nil {
				return
			}
			token, e := tokenFromName(t.ConnectionState().ServerName, g.suffix)
			if e != nil {
				return
			}
			for {
				t.SetReadDeadline(time.Now().Add(30 * time.Second))
				b, e := readWire(t)
				if e != nil {
					return
				}
				out, e := g.resolve(ctx, token, b, false)
				if e != nil {
					return
				}
				t.SetWriteDeadline(time.Now().Add(5 * time.Second))
				if writeWire(t, out) != nil {
					return
				}
			}
		}()
	}
}
func (g *gateway) serveQUIC(ctx context.Context, l *quic.Listener) {
	for {
		c, e := l.Accept(ctx)
		if e != nil {
			return
		}
		if !g.admit(c.RemoteAddr()) {
			c.CloseWithError(2, "busy")
			continue
		}
		go func() {
			defer g.release(c.RemoteAddr())
			defer c.CloseWithError(0, "")
			token, e := tokenFromName(c.ConnectionState().TLS.ServerName, g.suffix)
			if e != nil {
				return
			}
			for {
				s, e := c.AcceptStream(ctx)
				if e != nil {
					return
				}
				go func() {
					s.SetDeadline(time.Now().Add(15 * time.Second))
					b, e := readWire(s)
					if e != nil {
						s.CancelRead(2)
						s.CancelWrite(2)
						return
					}
					var tail [1]byte
					n, e := s.Read(tail[:])
					if n != 0 || e != io.EOF {
						s.CancelRead(2)
						s.CancelWrite(2)
						return
					}
					out, e := g.resolve(c.Context(), token, b, true)
					if e != nil {
						s.CancelWrite(2)
						return
					}
					if writeWire(s, out) != nil {
						s.CancelWrite(2)
						return
					}
					s.Close()
				}()
			}
		}()
	}
}
func env(k, d string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return d
}
func main() {
	certfile := env("TLS_CERT", "/certs/fullchain.pem")
	keyfile := env("TLS_KEY", "/certs/privkey.pem")
	suffix := env("DNS_SUFFIX", "tls.dns.maximoraverse.org")
	// Reload from disk at each handshake; renewed certificates need no process restart.
	load := func(*tls.ClientHelloInfo) (*tls.Certificate, error) {
		c, e := tls.LoadX509KeyPair(certfile, keyfile)
		return &c, e
	}
	if _, e := load(nil); e != nil {
		log.Fatal("TLS certificate unavailable")
	}
	tc := &tls.Config{MinVersion: tls.VersionTLS12, GetCertificate: load, NextProtos: []string{"dot"}}
	tc.GetConfigForClient = func(h *tls.ClientHelloInfo) (*tls.Config, error) {
		_, e := tokenFromName(h.ServerName, suffix)
		return nil, e
	}
	g := &gateway{url: strings.TrimSuffix(env("GATEWAY_URL", "http://127.0.0.1:18084"), "/"), suffix: suffix, client: &http.Client{Timeout: 14 * time.Second, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }, Transport: &http.Transport{MaxIdleConns: 64, MaxIdleConnsPerHost: 64, MaxConnsPerHost: 128}}, slots: make(chan struct{}, 128), ips: map[string]int{}}
	addr := env("LISTEN_ADDR", "127.0.0.1:1853")
	l, e := tls.Listen("tcp", addr, tc)
	if e != nil {
		log.Fatal("TCP listener unavailable")
	}
	qc := tc.Clone()
	qc.MinVersion = tls.VersionTLS13
	qc.NextProtos = []string{"doq"}
	q, e := quic.ListenAddr(addr, qc, &quic.Config{HandshakeIdleTimeout: 5 * time.Second, MaxIdleTimeout: 30 * time.Second, MaxIncomingStreams: 16, MaxIncomingUniStreams: -1, InitialStreamReceiveWindow: 65537, MaxStreamReceiveWindow: 65537, InitialConnectionReceiveWindow: 1 << 20, MaxConnectionReceiveWindow: 1 << 20, Allow0RTT: false})
	if e != nil {
		log.Fatal("UDP listener unavailable")
	}
	log.Print("DoT and DoQ listeners ready; query and credential logging disabled")
	ctx := context.Background()
	go g.serveTLS(ctx, l)
	g.serveQUIC(ctx, q)
}
