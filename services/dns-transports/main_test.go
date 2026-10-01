package main

import (
	"bytes"
	"context"
	"encoding/hex"
	"github.com/miekg/dns"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
)

func TestTokenHostname(t *testing.T) {
	raw := bytes.Repeat([]byte{0xab}, 32)
	label := strings.ToLower(b32.EncodeToString(raw))
	got, e := tokenFromName(label+".tls.example.org", "tls.example.org")
	if e != nil || got != hex.EncodeToString(raw) {
		t.Fatal("token roundtrip")
	}
	for _, s := range []string{label + ".evil.org", label + ".tls.example.org.evil", "extra." + label + ".tls.example.org", strings.Repeat("a", 64) + ".tls.example.org"} {
		if _, e := tokenFromName(s, "tls.example.org"); e == nil {
			t.Fatal("accepted invalid name")
		}
	}
}
func TestFraming(t *testing.T) {
	q := new(dns.Msg)
	q.SetQuestion("example.org.", dns.TypeA)
	wire, _ := q.Pack()
	var b bytes.Buffer
	if writeWire(&b, wire) != nil {
		t.Fatal("write")
	}
	got, e := readWire(&b)
	if e != nil || !bytes.Equal(got, wire) {
		t.Fatal("roundtrip")
	}
	for _, b := range [][]byte{{0}, {0, 2, 1, 2}, {0, 20, 1}} {
		if _, e := readWire(bytes.NewReader(b)); e == nil {
			t.Fatal("accepted malformed frame")
		}
	}
}
func TestEveryQueryReauthorizes(t *testing.T) {
	var blocked atomic.Bool
	var calls atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls.Add(1)
		if r.URL.Path != "/dns-query/test-token" || r.Method != "POST" {
			t.Error("incorrect backend routing")
		}
		if blocked.Load() {
			w.WriteHeader(403)
			return
		}
		q := new(dns.Msg)
		buf := new(bytes.Buffer)
		buf.ReadFrom(r.Body)
		q.Unpack(buf.Bytes())
		ans := new(dns.Msg)
		ans.SetReply(q)
		wire, _ := ans.Pack()
		w.Write(wire)
	}))
	defer srv.Close()
	g := &gateway{url: srv.URL, client: srv.Client(), slots: make(chan struct{}, 2)}
	q := new(dns.Msg)
	q.SetQuestion("example.org.", dns.TypeA)
	wire, _ := q.Pack()
	for _, denied := range []bool{false, true} {
		blocked.Store(denied)
		out, e := g.resolve(context.Background(), "test-token", wire, false)
		if e != nil {
			t.Fatal(e)
		}
		ans := new(dns.Msg)
		ans.Unpack(out)
		if denied && ans.Rcode != dns.RcodeRefused {
			t.Fatal("revocation bypass")
		}
		if !denied && ans.Rcode != 0 {
			t.Fatal("normal response")
		}
	}
	if calls.Load() != 2 {
		t.Fatal("cached auth")
	}
	if _, e := g.resolve(context.Background(), "test-token", wire, true); e == nil && q.Id != 0 {
		t.Fatal("DoQ accepted nonzero ID")
	}
	srv.Close()
	out, _ := g.resolve(context.Background(), "test-token", wire, false)
	ans := new(dns.Msg)
	ans.Unpack(out)
	if ans.Rcode != dns.RcodeServerFailure {
		t.Fatal("backend failure not closed")
	}
}
