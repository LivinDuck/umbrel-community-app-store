# DiscoPanel for Umbrel

Installs the unmodified upstream **DiscoPanel 2.0.15** interface and a dedicated
Docker engine for its Minecraft servers. The package supports AMD64 and ARM64.

## First use

1. Install **DiscoPanel** from the LivinDuck community store and open it.
2. Create your DiscoPanel administrator account in the normal upstream setup
   screen. Umbrel login protects this screen; there are no shared passwords.
3. Create a server, select its Minecraft version and server type, and start it.
   The first start downloads the Java image and server files, which can take
   several minutes. Watch progress in the console.
4. Connect in Minecraft Java Edition using your Umbrel address and the port
   shown for the server, for example `umbrel.local:25565`.

Use **25565–25574** for directly accessible game servers. The panel's normal
allocator starts at 25565. Ten direct ports are published; ports outside that
range will not be reachable from the LAN. Keep the number of running servers
within your device's available RAM and CPU capacity. Multiple configured
servers do not need to run simultaneously.

Install plugin jars into a Paper server's `plugins` folder using the file
manager. Modrinth modpacks work without an external account. CurseForge needs
your own optional API key. Features described in upstream's newer development
documentation may not yet be in this stable release.

## Friends and optional modules

For internet play, reserve your Umbrel's LAN address on your router, then forward
the selected TCP game port to that address. Friends join `public-IP:port`.
The package does not change your router or enable UPnP. Do not forward the panel
port just to let friends play.

Domain-based routing is optional: configure a proxy listener on a free port
inside 25565–25574 in DiscoPanel and point the game hostnames at your public IP.
Do not assign a direct server and a proxy listener the same port.

Optional modules allocate ports from **39410–39419**, published for TCP and UDP.
Geyser clients must use the actual assigned UDP port, rather than assuming 19132.
Module interfaces have their own authentication; they do not pass through
Umbrel's browser login. Additional manually configured ports must be within a
published range. Optional module functionality and every modpack are not
covered by the package smoke test.

## Persistence, updates and recovery

All persistent state lives under the app's `data` folder:

| Directory | Contents |
| --- | --- |
| `panel` | Accounts, settings, server files, worlds, mods and plugins |
| `backups` | Backups created by DiscoPanel or its backup module |
| `engine` | Dedicated Docker engine state and downloaded game images |
| `run` | Recreated local engine socket; excluded from Umbrel backups |
| `tmp` | Temporary uploads; excluded from Umbrel backups |

Stop the app before taking a filesystem backup of all its data. Restore the
panel, worlds and engine state together. Keep backups outside this app before
uninstalling: uninstalling deletes its data. An image downgrade does not undo
database migrations. App updates pin the panel and engine versions; server and
modpack version choices remain under your control in DiscoPanel.

The panel shares the dedicated engine's network namespace so consoles, server
status, and domain proxying can reach nested game containers. The engine has
privileged mode for nested container operation, but has no host Docker socket,
host networking or host filesystem mounts outside this app's data. Its API is
available only through an app-local Unix socket, never an unauthenticated TCP
listener. Upstream dynamically downloads the game images chosen in the panel.

## Validation

`tests/smoke_discopanel.py` runs the package services in disposable CI containers
on AMD64 and ARM64. It checks browser account setup, rejected unauthenticated
API access, multiple-server creation, a real Minecraft Java server's game port,
console/file access, and persistence after both services are recreated.

These checks are separate from a real Umbrel installation and app-proxy login
test. The package has not been installed on the owner's NAS as part of
publishing. Internet/router access and gameplay from a Minecraft client remain
untested.

The included icon is from upstream DiscoPanel, copyright Nicholas W. Heyer,
used under its MIT license; see `UPSTREAM-LICENSE`.
