# Phone access

The same workspace, sized for a phone, on your local network. Read something long, start a
turn, and approve the tool it wants — without walking back to the computer.

## Turn it on

1. In the panel, open **Phone access**.
2. It lists every LAN address plus a QR code for the first one.
3. On the phone: same Wi-Fi, scan or type the URL.

**Phone access** is always running while the gateway is up; the pane is where you read the
address, not a switch you have to flip. If the list is empty, the machine has no LAN
interface that the plugin can see — usually a VPN client or a firewall.

## What the URL looks like

```
http://192.168.1.23:47830/?t=<passphrase>
```

The passphrase is **fixed per installation** and stored in
`.runtime/mobile.json`. Only the IP changes, and only when your router hands out a new lease
— after a reboot, for example. When that happens, re-scan; do not reconfigure anything.

Port `47830` by default. Override with `CCP_MOBILE_PORT` if it collides with something.

## Why the passphrase is fixed and the token is not

Deliberately different, for two different jobs:

| | Phone passphrase | Relay token |
| :- | :- | :- |
| Scope | one LAN client | the Desktop panel |
| Stability | fixed, so a scanned QR keeps working | regenerated per install, refreshed on 403 |
| Threat | someone else on your Wi-Fi | a web page you happen to visit |

A passphrase that rotated every reboot would mean re-scanning every reboot, which is the
same as no passphrase because people would stop doing it. A web page, on the other hand,
can follow a redirect but cannot read a token out of local storage it never sees.

## What the phone can reach

A strict allow-list. Everything else — `/settings`, `/upgrade`, `/catalog` — is not mounted
on this port at all, even though it shares the router object:

```
/api/health              /api/models           /api/chat
/api/poll                /api/cancel           /api/approvals
/api/approvals/decide    /api/history          /api/history/session
/api/upload              /api/mobile
```

So a phone can read the workspace, run a turn, and answer approvals. It cannot change your
settings or trigger an upgrade — a lost phone is a read-and-approve risk, not a
reconfigure-your-machine risk.

## Approvals from the phone

This is the reason the feature exists. A turn that wants a tool blocks; the phone shows the
same card and the same three actions:

- **Allow** — this once
- **Always allow** — that tool for the rest of the session
- **Deny** — refuse, and the model sees the refusal

If nobody answers within the approval timeout, the request is auto-denied. The phone shows
the countdown, so you know how long you have.

## Language

The phone page is bilingual: `?lang=` wins, then `localStorage`, then `navigator.language`.
The passphrase-bearing URL does not need a language parameter — a Chinese phone gets Chinese,
an English phone gets English, and the toggle is in the header if you want to override it.

## Troubleshooting

| Symptom | Check |
| :- | :- |
| `ERR_CONNECTION_ABORTED` or a timeout | Same Wi-Fi? Guest networks and AP isolation block this. VPN on the phone? Turn it off. |
| Page loads but says a passphrase is required | The `?t=` part of the URL was stripped. Re-scan, or append it manually. |
| Worked yesterday, not today | The IP changed. Re-scan from the panel. |
| Panel shows no addresses | The machine has no LAN IP the plugin can read — usually a VPN, or a firewall hiding the interface. |
| Nothing loads but the port is open | Only the allow-listed routes answer; a hand-typed `/settings` returns 404 by design. |
