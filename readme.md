# AWiM Deck
This plugin integrates [awim-client](https://github.com/rotlir/awim-client) into the Steam Deck Gamescope shell, allowing you to conveniently interact with the application and use your phone as a microphone for the console.

# Install
You can download the zip archive directly from the [releases](https://github.com/ergolyam/awim-deck/releases) and install it via developer mode in decky loader.

# Build
Use `pnpm` to build the project. For an isolated build of the [awim-client](https://github.com/rotlir/awim-client) binary file, I recommend installing `Docker` or `Podman`.

- Clone the repository and install dependencies:
    ```shell
    git clone https://github.com/ergolyam/awim-deck.git
    cd awim-deck
    pnpm install
    ```

- Build the project:
    ```shell
    pnpm run build
    ```
    > After successful compilation, you will receive a `zip` archive in the `out` directory, which can be installed in decky loader via developer mode.

# Screenshots
![screenshot](assets/screenshot.jpg)
