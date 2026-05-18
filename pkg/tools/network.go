package tools

import (
	"context"
	"fmt"
	"net"
	"os"
	"runtime"
	"strings"
)

// NetworkTool reports the board's network state in a read-only, structured way.
// Returns interface names, IPs, default gateway, hostname. Does NOT modify state.
//
// Narrowly scoped: no shell-out for "more info"; only the Go stdlib `net`
// package + a couple of /proc reads.
type NetworkTool struct{}

func NewNetworkTool() *NetworkTool { return &NetworkTool{} }

func (t *NetworkTool) Name() string { return "network" }

func (t *NetworkTool) Description() string {
	return "Report the Uno Q's network state (read-only). Returns hostname, IP addresses per interface, " +
		"the default gateway, and whether the board is connected to the internet. Useful for answering " +
		"'what is my board's IP for SSH?' and 'is the board online?' without the user opening a terminal."
}

func (t *NetworkTool) Parameters() map[string]any {
	return map[string]any{
		"type": "object",
		"properties": map[string]any{
			"action": map[string]any{
				"type":        "string",
				"enum":        []string{"summary", "interfaces", "gateway"},
				"description": "summary (default) = hostname + per-interface IPs + gateway; interfaces = IPs only; gateway = default route only.",
			},
		},
		"required": []string{},
	}
}

func (t *NetworkTool) Execute(_ context.Context, args map[string]any) *ToolResult {
	if runtime.GOOS != "linux" {
		return ErrorResult("network tool is only supported on Linux (Arduino Uno Q runs Debian).")
	}
	action, _ := args["action"].(string)
	if action == "" {
		action = "summary"
	}
	switch action {
	case "summary":
		return t.summary()
	case "interfaces":
		return t.interfaces()
	case "gateway":
		return t.gateway()
	default:
		return ErrorResult(fmt.Sprintf("unknown action: %s (use summary, interfaces, or gateway)", action))
	}
}

func (t *NetworkTool) summary() *ToolResult {
	var out strings.Builder
	host, _ := os.Hostname()
	out.WriteString(fmt.Sprintf("Hostname: %s\n\n", host))
	out.WriteString(t.interfacesText())
	out.WriteString("\n")
	out.WriteString(t.gatewayText())
	return NewToolResult(out.String())
}

func (t *NetworkTool) interfaces() *ToolResult {
	return NewToolResult(t.interfacesText())
}

func (t *NetworkTool) gateway() *ToolResult {
	return NewToolResult(t.gatewayText())
}

func (t *NetworkTool) interfacesText() string {
	var out strings.Builder
	out.WriteString("Interfaces:\n")
	ifaces, err := net.Interfaces()
	if err != nil {
		out.WriteString(fmt.Sprintf("  (error listing: %v)\n", err))
		return out.String()
	}
	for _, ifc := range ifaces {
		// Skip down interfaces with no addresses
		addrs, _ := ifc.Addrs()
		if ifc.Flags&net.FlagUp == 0 && len(addrs) == 0 {
			continue
		}
		flags := ""
		if ifc.Flags&net.FlagUp != 0 {
			flags = "up"
		} else {
			flags = "down"
		}
		if ifc.Flags&net.FlagLoopback != 0 {
			flags += ",loopback"
		}
		out.WriteString(fmt.Sprintf("  %s [%s, MAC %s]\n", ifc.Name, flags, ifc.HardwareAddr))
		for _, a := range addrs {
			out.WriteString(fmt.Sprintf("    %s\n", a.String()))
		}
	}
	return out.String()
}

// gatewayText reads /proc/net/route and decodes the default gateway entry.
// /proc/net/route columns: Iface Destination Gateway Flags ...
// Destination=00000000 marks the default route.
func (t *NetworkTool) gatewayText() string {
	const path = "/proc/net/route"
	data, err := os.ReadFile(path)
	if err != nil {
		return fmt.Sprintf("Default gateway: (cannot read %s: %v)\n", path, err)
	}
	lines := strings.Split(string(data), "\n")
	for _, line := range lines[1:] { // skip header
		fields := strings.Fields(line)
		if len(fields) < 4 {
			continue
		}
		iface := fields[0]
		destHex := fields[1]
		gwHex := fields[2]
		if destHex != "00000000" {
			continue
		}
		gw := hexToIP(gwHex)
		return fmt.Sprintf("Default gateway: %s via %s\n", gw, iface)
	}
	return "Default gateway: (none — board is offline or routing not yet up)\n"
}

// hexToIP decodes the little-endian hex IP that /proc/net/route uses
// (e.g. "0101A8C0" → "192.168.1.1").
func hexToIP(h string) string {
	if len(h) != 8 {
		return h
	}
	b := make([]byte, 4)
	for i := 0; i < 4; i++ {
		_, _ = fmt.Sscanf(h[6-2*i:8-2*i], "%2x", &b[i])
	}
	return fmt.Sprintf("%d.%d.%d.%d", b[0], b[1], b[2], b[3])
}
