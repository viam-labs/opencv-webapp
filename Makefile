PYTHON ?= python3
TARBALL := module.tar.gz
LIB_DIR := lib

.PHONY: setup build clean

setup:
	rm -rf $(LIB_DIR)
	$(PYTHON) -m pip install --target $(LIB_DIR) --no-compile --no-cache-dir -r requirements.txt

build: $(TARBALL)

$(TARBALL):
	tar -czf $(TARBALL) README.md LICENSE meta.json requirements.txt bin src $(LIB_DIR)

clean:
	rm -f $(TARBALL)
	rm -rf $(LIB_DIR)

