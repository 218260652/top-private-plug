package main

import (
    "context"
    "crypto/ecdsa"
    "crypto/elliptic"
    "crypto/rand"
    "crypto/tls"
    "crypto/x509"
    "encoding/json"
    "encoding/pem"
    "fmt"
    "io"
    "math/big"
    "net"
    "net/http"
    "net/http/httptest"
    "net/url"
    "os"
    "strconv"
    "strings"
    "sync/atomic"
    "time"

    corenet "github.com/xtls/xray-core/common/net"
    core "github.com/xtls/xray-core/core"
    "github.com/xtls/xray-core/infra/conf/serial"
    _ "github.com/xtls/xray-core/main/distro/all"
)

type object = map[string]interface{}

func instance(config object) *core.Instance {
    b, err := json.Marshal(config); if err != nil { panic(err) }
    c, err := serial.LoadJSONConfig(strings.NewReader(string(b))); if err != nil { panic(err) }
    inst, err := core.New(c); if err != nil { panic(err) }
    if err := inst.Start(); err != nil { panic(err) }
    return inst
}

func main() {
    original, err := io.ReadAll(os.Stdin); if err != nil { panic(err) }
    var received, connected atomic.Int32
    origin := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        received.Add(1)
        fmt.Fprint(w, "through-vless")
    })); defer origin.Close()
    roots := x509.NewCertPool(); roots.AddCert(origin.Certificate())
    _, originPortText, err := net.SplitHostPort(strings.TrimPrefix(origin.URL, "https://")); if err != nil { panic(err) }
    originPort, err := strconv.Atoi(originPortText); if err != nil { panic(err) }

    key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader); if err != nil { panic(err) }
    cert := &x509.Certificate{SerialNumber: big.NewInt(17), DNSNames: []string{"fixture.invalid"},
        NotBefore: time.Now().Add(-time.Hour), NotAfter: time.Now().Add(time.Hour),
        KeyUsage: x509.KeyUsageDigitalSignature, ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth}}
    der, err := x509.CreateCertificate(rand.Reader, cert, cert, &key.PublicKey, key); if err != nil { panic(err) }
    encodedKey, err := x509.MarshalECPrivateKey(key); if err != nil { panic(err) }
    certPEM := string(pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der}))
    keyPEM := string(pem.EncodeToMemory(&pem.Block{Type: "EC PRIVATE KEY", Bytes: encodedKey}))
    reservation, err := net.Listen("tcp", "127.0.0.1:0"); if err != nil { panic(err) }
    serverPort := reservation.Addr().(*net.TCPAddr).Port; reservation.Close()
    serverAddress := net.JoinHostPort("127.0.0.1", strconv.Itoa(serverPort))
    server := instance(object{
        "log": object{"loglevel": "debug"},
        "inbounds": []object{{"listen": "127.0.0.1", "port": serverPort, "protocol": "vless",
            "settings": object{"clients": []object{{"id": "00000000-0000-4000-8000-000000000001"}}, "decryption": "none"},
            "streamSettings": object{"network": "tcp", "security": "tls", "tlsSettings": object{"certificates": []object{{
                "certificate": strings.Split(certPEM, "\n"), "key": strings.Split(keyPEM, "\n")}}}}}},
        // The current core blocks private destinations from proxy inbounds by default.
        // Permit only this fixture's exact loopback origin; do not change app policy.
        "outbounds": []object{{"protocol": "freedom", "settings": object{"finalRules": []object{{
            "action": "allow", "ip": []string{"127.0.0.1/32"}, "port": originPort}}}}},
    }); defer server.Close()

    var reject atomic.Bool
    proxy := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        if reject.Load() || r.Method != "CONNECT" || r.Host != serverAddress ||
            r.Header.Get("User-Agent") != "tpp-loopback-fixture" || r.Header.Get("X-iorg-bsid") != "fixture-only" {
            http.Error(w, "fixture proxy rejected request", http.StatusForbidden); return
        }
        remote, err := net.DialTimeout("tcp", r.Host, 3*time.Second)
        if err != nil { http.Error(w, "fixture upstream unavailable", 502); return }
        client, rw, err := w.(http.Hijacker).Hijack()
        if err != nil { remote.Close(); return }
        defer client.Close(); defer remote.Close()
        client.SetDeadline(time.Now().Add(15*time.Second)); remote.SetDeadline(time.Now().Add(15*time.Second))
        connected.Add(1)
        rw.WriteString("HTTP/1.1 200 Connection established\r\n\r\n"); rw.Flush()
        done := make(chan struct{})
        go func() { io.Copy(remote, rw.Reader); remote.Close(); close(done) }()
        io.Copy(client, remote); client.Close(); <-done
    })); defer proxy.Close()
    _, proxyPort, err := net.SplitHostPort(proxy.Listener.Addr().String()); if err != nil { panic(err) }
    proxyNumber, err := strconv.Atoi(proxyPort); if err != nil { panic(err) }

    for _, mode := range []string{"direct-working", "working", "verified-TLS-rejects-self-signed", "wrong-UUID", "proxy-rejects"} {
        var config object
        if err := json.Unmarshal(original, &config); err != nil { panic(err) }
        delete(config, "_fixture_control")
        outbounds := config["outbounds"].([]interface{})
        tunnel := outbounds[0].(map[string]interface{})
        node := tunnel["settings"].(map[string]interface{})["vnext"].([]interface{})[0].(map[string]interface{})
        node["port"] = serverPort
        if mode == "direct-working" { delete(tunnel["streamSettings"].(map[string]interface{}), "sockopt") }
        upstream := outbounds[1].(map[string]interface{})["settings"].(map[string]interface{})["servers"].([]interface{})[0].(map[string]interface{})
        upstream["port"] = proxyNumber
        if mode == "verified-TLS-rejects-self-signed" {
            tunnel["streamSettings"].(map[string]interface{})["tlsSettings"].(map[string]interface{})["allowInsecure"] = false
        }
        if mode == "wrong-UUID" {
            node["users"].([]interface{})[0].(map[string]interface{})["id"] = "00000000-0000-4000-8000-000000000002"
        }
        reject.Store(mode == "proxy-rejects")
        before := received.Load()
        clientCore := instance(config)
        tr := &http.Transport{TLSClientConfig: &tls.Config{RootCAs: roots},
            DialContext: func(ctx context.Context, network, address string) (net.Conn, error) {
                destination, err := corenet.ParseDestination(network+":"+address)
                if err != nil { return nil, err }
                return core.Dial(ctx, clientCore, destination)
            }}
        response, requestErr := (&http.Client{Transport: tr, Timeout: 8*time.Second}).Get(origin.URL+"/health")
        body := ""
        if response != nil { b, _ := io.ReadAll(response.Body); response.Body.Close(); body = string(b) }
        tr.CloseIdleConnections(); clientCore.Close()
        if mode == "working" || mode == "direct-working" {
            fmt.Println("fixture origin requests",received.Load(),"proxy connections",connected.Load())
            if requestErr != nil || response == nil || response.StatusCode != 200 || body != "through-vless" || received.Load() != before+1 || (mode == "working" && connected.Load() < 1) {
                panic(fmt.Sprintf("full VLESS HTTP/TLS chain failed: %v body=%q", requestErr, body))
            }
        } else if requestErr == nil || received.Load() != before {
            panic("negative control leaked or succeeded: "+mode)
        }
        fmt.Println("PASS:", mode)
    }
    // Exercise the actual Java-generated bootstrap policy through a real HTTP
    // CONNECT inbound. No TUN or ordinary-device-traffic inbound is installed.
    var boot object
    if err := json.Unmarshal(original, &boot); err != nil { panic(err) }
    policy := boot["_fixture_control"].(map[string]interface{}); delete(boot, "_fixture_control")
    bootOut := boot["outbounds"].([]interface{})
    bootNode := bootOut[0].(map[string]interface{})["settings"].(map[string]interface{})["vnext"].([]interface{})[0].(map[string]interface{})
    bootNode["port"] = serverPort
    bootUpstream := bootOut[1].(map[string]interface{})["settings"].(map[string]interface{})["servers"].([]interface{})[0].(map[string]interface{})
    bootUpstream["port"] = proxyNumber
    reservation, err = net.Listen("tcp", "127.0.0.1:0"); if err != nil { panic(err) }
    controlPort := reservation.Addr().(*net.TCPAddr).Port; reservation.Close()
    inbound := policy["inbound"].(map[string]interface{}); inbound["port"] = controlPort
    if inbound["listen"] != "127.0.0.1" || inbound["protocol"] != "http" { panic("unsafe bootstrap listener") }
    rules := policy["rules"].([]interface{}); rules[0].(map[string]interface{})["port"] = strconv.Itoa(originPort)
    boot["inbounds"] = []interface{}{inbound}
    boot["routing"] = object{"domainStrategy":"AsIs", "rules":rules}
    reject.Store(false)
    bootCore := instance(boot); defer bootCore.Close()
    localProxy, _ := url.Parse(fmt.Sprintf("http://127.0.0.1:%d",controlPort))
    transport := &http.Transport{Proxy:http.ProxyURL(localProxy), TLSClientConfig:&tls.Config{RootCAs:roots, ServerName:"127.0.0.1"}}
    bootClient := &http.Client{Transport:transport, Timeout:8*time.Second}
    before := received.Load()
    response, err := bootClient.Get(origin.URL+"/health")
    if err != nil { panic(fmt.Sprintf("account HTTPS through bootstrap failed: %v",err)) }
    body, err := io.ReadAll(response.Body); response.Body.Close()
    if err != nil || string(body)!="through-vless" || received.Load()!=before+1 { panic("bootstrap account check did not traverse VLESS") }
    fmt.Println("PASS: bootstrap account HTTPS through restricted loopback proxy")
    before=received.Load()
    denied, deniedErr := bootClient.Get(strings.Replace(origin.URL,"127.0.0.1","localhost",1)+"/health")
    if denied!=nil { denied.Body.Close() }
    if deniedErr==nil || received.Load()!=before { panic("bootstrap leaked to an unapproved target") }
    transport.CloseIdleConnections()
    fmt.Println("PASS: bootstrap rejects other targets before account approval")

}
