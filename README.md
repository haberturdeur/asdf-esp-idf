# asdf-esp-idf

An [asdf](https://asdf-vm.com/) plugin for Espressif ESP-IDF.

This plugin deliberately does **not** clone ESP-IDF with git. It installs from
the `esp-idf-vX.Y.Z.zip` assets attached to
[`espressif/esp-idf` releases](https://github.com/espressif/esp-idf/releases).
Those release assets include ESP-IDF submodules; GitHub's generated "Source
code" archives do not.

## Requirements

- `bash`
- `curl`
- `unzip`
- `python3`
- ESP-IDF's normal host dependencies for your OS

## Install the plugin

```sh
asdf plugin add esp-idf /home/tom/asdf-esp-idf
```

When published, replace `/home/tom/asdf-esp-idf` with the plugin git URL.

## Install ESP-IDF

```sh
asdf list all esp-idf
asdf install esp-idf latest
asdf set -u esp-idf latest
```

Or install a concrete version:

```sh
asdf install esp-idf 5.5.4
asdf set -u esp-idf 5.5.4
```

## Activate ESP-IDF

Shell scripts cannot alter their parent shell unless they are sourced, so use
one of these forms:

```sh
. "$(asdf where esp-idf)/get_idf"
```

or source the selected shim target:

```sh
. "$(asdf which get_idf)"
```

If you want a normal `get_idf` command that activates the current shell, add a
shell function to your shell rc file:

```sh
get_idf() { . "$(asdf which get_idf)"; }
```

The installed `get_idf` helper sources ESP-IDF's `export.sh` and sets `IDF_PATH`
to the selected asdf install.

## Notes

- The plugin lists only release zip assets named `esp-idf-v*.zip`.
- `asdf install` runs ESP-IDF's `install.sh` after extraction to install the
  required toolchains under Espressif's normal locations.
