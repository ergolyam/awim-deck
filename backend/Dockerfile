FROM docker.io/archlinux:latest

RUN pacman-key --init
RUN pacman-key --populate archlinux
RUN pacman -Syu --noconfirm
RUN pacman -S --noconfirm --needed base-devel patch pipewire wget tar

# entrypoint.sh should always be located in the backend folder
ENTRYPOINT [ "/backend/entrypoint.sh" ]
