AWIM_COMMIT := 98def5b028d62feaf6e5fbbf44964d171ca4e751
AWIM_REPO_URL := https://github.com/rotlir/awim-client/archive/$(AWIM_COMMIT).tar.gz
BUILD_ROOT := /tmp/awim-client-build
ARCHIVE_PATH := $(BUILD_ROOT)/awim-client-$(AWIM_COMMIT).tar.gz
SOURCE_DIR := $(BUILD_ROOT)/awim-client-$(AWIM_COMMIT)
OUTPUT_DIR := ./out
OUTPUT_BIN := $(OUTPUT_DIR)/awim
AWIM_PATCH := $(CURDIR)/patches/awim-client-status.patch

.PHONY: all clean build-awim

all: build-awim

build-awim:
	rm -rf $(BUILD_ROOT)
	mkdir -p $(BUILD_ROOT)
	wget -O $(ARCHIVE_PATH) $(AWIM_REPO_URL)
	tar xvf $(ARCHIVE_PATH) -C $(BUILD_ROOT)
	patch -d $(SOURCE_DIR) -p1 < $(AWIM_PATCH)
	$(MAKE) -C $(SOURCE_DIR)
	mkdir -p $(OUTPUT_DIR)
	cp $(SOURCE_DIR)/awim $(OUTPUT_BIN)
	chmod +x $(OUTPUT_BIN)

clean:
	rm -rf $(BUILD_ROOT)
	rm -rf $(OUTPUT_DIR)
