# GNU Make. Windows cross-compiler uses Linux-hosted MinGW-w64.
CC ?= cc
MODE ?= release
EXE ?=
BUILD := build/$(MODE)
SOURCES := $(filter-out examples/09_exports.c,$(wildcard examples/*.c))
TARGETS := $(patsubst examples/%.c,$(BUILD)/%$(EXE),$(SOURCES))
COMMON := -std=c11 -Wall -Wextra -Wpedantic
ifeq ($(MODE),debug)
  CFLAGS += $(COMMON) -O0 -g3
else
  CFLAGS += $(COMMON) -O2 -flto -DNDEBUG -fvisibility=hidden -ffunction-sections -fdata-sections
endif
LDLIBS += -lm
.PHONY: all check windows inspect strip clean advanced
all: $(TARGETS)
$(BUILD):
	mkdir -p $@
$(BUILD)/%$(EXE): examples/%.c | $(BUILD)
	$(CC) $(CFLAGS) $< -o $@ $(LDFLAGS) $(LDLIBS)
check: all
	@set -e; for binary in $(TARGETS); do \
	    case "$$binary" in *10_entropy*|*11_integrity*) "$$binary" README.md ;; *) "$$binary" ;; esac; \
	done
advanced: $(BUILD)/13_vm_advanced$(EXE) $(BUILD)/14_state_machine$(EXE)
windows:
	$(MAKE) CC=x86_64-w64-mingw32-gcc EXE=.exe MODE=$(MODE) all
inspect: all
	@for binary in $(TARGETS); do \
	  echo "$$binary"; file "$$binary"; size "$$binary"; \
	done
strip: all
	strip --strip-unneeded $(TARGETS)
clean:
	$(RM) -r build
