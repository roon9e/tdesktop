# build-system

Produces a rebranded Telegram Desktop Windows build from clean upstream
sources. Except for a small build baseline commit, the repository is
untouched upstream code: all branding is applied at build time by scripts in
this folder.

## Layout

| File | Purpose |
| --- | --- |
| `branding/branding.json` | Branding values (name, scheme, host, datacenter). |
| `branding/server_rsa.pub` | PEM (PKCS#1) RSA public key for datacenter authentication. |
| `apply_branding.py` | Rewrites brand tokens in the sources in place. |
| `generate_icons.py` | Regenerates `Telegram/Resources/art` icons from `logo.png`. |
| `build_local.ps1` | Local Windows build entry point (VS 2026 x64 Native Tools prompt). |

## Workflow

A CI workflow (`.github/workflows/build.yml`) does the same as a local build:

1. checkout with submodules (recursive)
2. `Telegram/build/prepare/win.bat skip-release silent` (builds dependencies)
3. `Telegram/configure.bat` (generates `version.h` from `Telegram/build/version`)
4. `build-system/apply_branding.py` (after configure, because configure
   regenerates `version.h`)
5. `cmake --build out --config Debug --target Telegram`

The library build stages force `PlatformToolset=v145` but let MSBuild resolve
the installed v145 toolset version itself (no pinned `VCToolsVersion`), so any
Visual Studio 2026 installation works. The Windows 7-era `v144.4` toolset
(reached through `vcvars_ver=14.44`) is intentionally not used: it ships no
`atlmfc` folder, breaking the breakpad build stage; the modern v145 toolset
always includes ATL/MFC. Do not initialize the prompt with `vcvars_ver=14.44`.

## Branding

`branding/branding.json`:

```json
{
  "general": {
    "app_name": "Teleram Desktop",
    "app_name_short": "TeleramDesktop",
    "protocol_name": "Teleram Link",
    "url_scheme": "owpg",
    "host": "teleram.ru",
    "company_name": "My Company"
  },
  "datacenter": { "id": 2, "ip": "1.2.3.4", "port": 443 }
}
```

* `app_name` — `AppName` in `core/version.h` and the Windows
  FileDescription/ProductName metadata.
* `app_name_short` — `QApplication::setApplicationName` (no spaces).
* `protocol_name` — the `.protocolName` used for the URL scheme registration.
* `url_scheme` — replaces `tg://` (default `owpg`).
* `host` — replaces `t.me` / `telegram.me` / `telegram.dog`
  (default `teleram.ru`).
* `company_name` — optional; when present also replaces the Windows
  `CompanyName` metadata.
* `datacenter` — the built-in datacenter (id/ip/port) written into
  `mtproto_dc_options.cpp`; the RSA key comes from `server_rsa.pub`.

A `logo.png` placed at `Telegram/Resources/art/logo.png` replaces the app
icons (the `.ico` and all `icon*.png` files are regenerated from it). Without
it the stock icons are kept.

## apply_branding.py

* Global token passes over `Telegram/SourceFiles` and `lang.strings`:
  `tg://` -> scheme, `t.me` / `telegram.me` / `telegram.dog` -> host
  (word-boundary aware, so identifiers are not corrupted).
* Anchored, fail-loud replacements for the exact spots that need contextual
  edits: `version.h`, `launcher.cpp`, `application.cpp`, `mtproto_config.h`,
  `mtproto_dc_options.cpp` (datacenters + RSA key blocks), `local_url_handlers`,
  `connection_box`, `click_handler_types`, `main_session`, `choose_filter_box`,
  `lib_base/base/qthelp_url.cpp`, `lib_ui/ui/text/text_entity.cpp` and the
  Windows `.rc` metadata files. If an anchor is missing the script exits with
  an error (unless the replacement is already in place, so the script is
  idempotent).
* Preserves the original line endings (CRLF on a native Windows checkout) and
  UTF-8 encoding (no BOM).

`--dry-run` reports what would change without writing.

## Verification

Run `apply_branding.py` on a fresh clone with clean submodules, then compare
`git diff` against the reference fork. The only expected differences from the
reference implementation are deliberate fixes:

* `click_handler_types.cpp` unwraps short `t.me` links in the confirmation
  whitelist to the new host (upstream only handled `tg://`).
* `choose_filter_box.cpp` fixes the `mid(...)` cut length to match the new
  host length.
* `main_session.cpp` collapses the comment to the single new host.
* Windows `.rc` metadata is rebranded (the reference fork named it
  `NexGram Desktop`, keeping `CompanyName`).
* there are no commented-out "old regex" leftovers.