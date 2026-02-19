# AWiM Deck
This plugin integrates [awim-client](https://github.com/rotlir/awim-client) into the Steam Deck Gamescope shell, allowing you to conveniently interact with the application and use your phone as a microphone for the console.

### Initial Setup

1. **Clone the repository**: Clone this repository using `git clone`.
3. **Download Dependencies**: Download the required dependencies using `pnpm`.

```shell
git clone https://github.com/ergolyam/awim-deck.git
cd awim-deck
pnpm install
```

# Build
Use `pnpm` to build the project. For an isolated build of the [awim-client](https://github.com/rotlir/awim-client) binary file, I recommend installing `Docker` or `Podman`.

```shell
pnpm run build
```
- After successful compilation, you will receive a `zip` archive in the `out` directory, which can be installed in decky loader via developer mode.
