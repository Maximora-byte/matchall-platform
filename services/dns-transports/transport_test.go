package main

import (
	"context"
	"crypto/tls"
	"github.com/miekg/dns"
	"github.com/quic-go/quic-go"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func TestLiveTLSAndQUICRevocation(t *testing.T) {
	certPath := os.Getenv("TEST_CERT")
	if certPath == "" {
		t.Skip("certificate not provided")
	}
	cert, err := tls.LoadX509KeyPair(certPath, os.Getenv("TEST_KEY"))
	if err != nil {
		t.Fatal(err)
	}
	var denied atomic.Bool
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if denied.Load() {
			w.WriteHeader(403)
			return
		}
		b, _ := io.ReadAll(r.Body)
		q := new(dns.Msg)
		q.Unpack(b)
		a := new(dns.Msg)
		a.SetReply(q)
		out, _ := a.Pack()
		w.Write(out)
	}))
	defer backend.Close()
	g := &gateway{url: backend.URL, suffix: "tls.dns.maximoraverse.org", client: backend.Client(), slots: make(chan struct{}, 4), ips: map[string]int{}}
	server := &tls.Config{Certificates: []tls.Certificate{cert}, MinVersion: tls.VersionTLS12, NextProtos: []string{"dot"}}
	server.GetConfigForClient = func(h *tls.ClientHelloInfo) (*tls.Config, error) {
		_, e := tokenFromName(h.ServerName, g.suffix)
		return nil, e
	}
	name := strings.ToLower(b32.EncodeToString(make([]byte, 32))) + "." + g.suffix
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	tl, err := tls.Listen("tcp", "127.0.0.1:0", server)
	if err != nil {
		t.Fatal(err)
	}
	defer tl.Close()
	go g.serveTLS(ctx, tl)
	c, err := tls.Dial("tcp", tl.Addr().String(), &tls.Config{ServerName: name, MinVersion: tls.VersionTLS12, NextProtos: []string{"dot"}})
	if err != nil {
		t.Fatal(err)
	}
	defer c.Close()
	c.SetDeadline(time.Now().Add(10 * time.Second))
	query := new(dns.Msg)
	query.SetQuestion("example.org.", dns.TypeA)
	query.Id = 0
	wire, _ := query.Pack()
	check := func(b []byte, e error, blocked bool) {
		t.Helper()
		if e != nil {
			t.Fatal(e)
		}
		a := new(dns.Msg)
		if a.Unpack(b) != nil {
			t.Fatal("bad answer")
		}
		want := 0
		if blocked {
			want = dns.RcodeRefused
		}
		if a.Rcode != want {
			t.Fatalf("rcode=%d want=%d", a.Rcode, want)
		}
	}
	for _, blocked := range []bool{false, true} {
		denied.Store(blocked)
		if e := writeWire(c, wire); e != nil {
			t.Fatal(e)
		}
		b, e := readWire(c)
		check(b, e, blocked)
	}
	qc := server.Clone()
	qc.MinVersion = tls.VersionTLS13
	qc.NextProtos = []string{"doq"}
	ql, err := quic.ListenAddr("127.0.0.1:0", qc, &quic.Config{Allow0RTT: false})
	if err != nil {
		t.Fatal(err)
	}
	defer ql.Close()
	go g.serveQUIC(ctx, ql)
	conn, err := quic.DialAddr(ctx, ql.Addr().String(), &tls.Config{ServerName: name, MinVersion: tls.VersionTLS13, NextProtos: []string{"doq"}}, nil)
	if err != nil {
		t.Fatal(err)
	}
	defer conn.CloseWithError(0, "")
	for _, blocked := range []bool{false, true} {
		denied.Store(blocked)
		s, e := conn.OpenStreamSync(ctx)
		if e != nil {
			t.Fatal(e)
		}
		s.SetDeadline(time.Now().Add(5 * time.Second))
		if e = writeWire(s, wire); e != nil {
			t.Fatal(e)
		}
		s.Close()
		b, e := readWire(s)
		check(b, e, blocked)
	}
	invalid, err := tls.DialWithDialer(&net.Dialer{Timeout: time.Second}, "tcp", tl.Addr().String(), &tls.Config{ServerName: "invalid." + g.suffix})
	if err == nil {
		invalid.Close()
		t.Fatal("invalid hostname accepted")
	}
}
