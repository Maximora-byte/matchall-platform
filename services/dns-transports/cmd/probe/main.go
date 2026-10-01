package main

import (
	"context"
	"crypto/tls"
	"encoding/base32"
	"encoding/binary"
	"encoding/hex"
	"fmt"
	"github.com/miekg/dns"
	"github.com/quic-go/quic-go"
	"io"
	"os"
	"strings"
	"time"
)

func main() {
	raw, e := os.ReadFile(os.Getenv("TOKEN_FILE"))
	if e != nil {
		panic("token file unavailable")
	}
	token, e := hex.DecodeString(strings.TrimSpace(string(raw)))
	if e != nil || len(token) != 32 {
		panic("invalid token")
	}
	name := strings.ToLower(base32.StdEncoding.WithPadding(base32.NoPadding).EncodeToString(token)) + ".tls.dns.maximoraverse.org"
	addr := os.Getenv("PROBE_ADDR")
	if addr == "" {
		addr = "127.0.0.1:1853"
	}
	domain := os.Getenv("PROBE_DOMAIN")
	if domain == "" {
		domain = "example.org."
	}
	q := new(dns.Msg)
	q.SetQuestion(dns.Fqdn(domain), dns.TypeA)
	q.Id = 0
	b, _ := q.Pack()
	frame := make([]byte, len(b)+2)
	binary.BigEndian.PutUint16(frame, uint16(len(b)))
	copy(frame[2:], b)
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	read := func(r io.Reader, proto string) {
		var size [2]byte
		if _, e := io.ReadFull(r, size[:]); e != nil {
			panic("response length failed")
		}
		b := make([]byte, binary.BigEndian.Uint16(size[:]))
		if _, e := io.ReadFull(r, b); e != nil {
			panic("response read failed")
		}
		a := new(dns.Msg)
		if a.Unpack(b) != nil {
			panic("invalid response")
		}
		fmt.Printf("%s rcode=%s answers=%d\n", proto, dns.RcodeToString[a.Rcode], len(a.Answer))
		want := os.Getenv("EXPECT_RCODE")
		if want != "" && dns.RcodeToString[a.Rcode] != want {
			panic("unexpected response code")
		}
	}
	tc := &tls.Config{ServerName: name, MinVersion: tls.VersionTLS12, NextProtos: []string{"dot"}}
	c, e := tls.Dial("tcp", addr, tc)
	if e != nil {
		panic("DoT handshake failed")
	}
	c.SetDeadline(time.Now().Add(15 * time.Second))
	c.Write(frame)
	read(c, "DoT")
	c.Close()
	tc = tc.Clone()
	tc.MinVersion = tls.VersionTLS13
	tc.NextProtos = []string{"doq"}
	conn, e := quic.DialAddr(ctx, addr, tc, nil)
	if e != nil {
		panic("DoQ handshake failed")
	}
	defer conn.CloseWithError(0, "")
	s, e := conn.OpenStreamSync(ctx)
	if e != nil {
		panic("DoQ stream failed")
	}
	s.SetDeadline(time.Now().Add(15 * time.Second))
	s.Write(frame)
	s.Close()
	read(s, "DoQ")
}
