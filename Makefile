PYTHON ?= python3
TARBALL := module.tar.gz
LIB_DIR := lib

.PHONY: setup build clean ensure-dist

setup:
	rm -rf $(LIB_DIR)
	$(PYTHON) -m pip install --target $(LIB_DIR) --no-compile --no-cache-dir -r requirements.txt

build: setup ensure-dist
	tar -czf $(TARBALL) \
		meta.json \
		run.sh \
		requirements.txt \
		README.md \
		dist \
		opencv_webapp \
		$(LIB_DIR)

clean:
	rm -f $(TARBALL)
	rm -rf $(LIB_DIR)

ensure-dist:
	@test -d dist || (echo "dist/ not found. Run 'npm run build' before packaging." && exit 1)

