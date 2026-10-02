# LocalDrop — Homebrew formula for macOS.
#
# Published to the personal tap:
#     brew tap abhi-subedi/localdrop
#     brew install localdrop
#
# CI regenerates this file on every release (.github/workflows/release.yml),
# substituting the version and the per-architecture sha256, so it always points
# at a real, checksummed artefact.
#
# Homebrew's rules shape everything below: no `sudo`, no writing outside the
# prefix, no service auto-install. LocalDrop runs as a user-level daemon you
# start yourself, which is the right default for a LAN file server anyway.
#
# There are no runtime dependencies: the binary is self-contained, and the
# embedded PostgreSQL it starts needs nothing installed.

class Localdrop < Formula
  desc "Self-hosted, local-network-first file sharing"
  homepage "https://github.com/Abhi-Subedi/LocalDrop"
  version "1.1.0"
  license "AGPL-3.0-only"

  livecheck do
    url :stable
    strategy :github_latest
  end

  # Homebrew does not cross-install binaries, so pick the artefact that matches
  # the machine. (Bottles would be nicer; they need an Apple Silicon runner to
  # build and a signed notarisation ticket, so releases ship raw tarballs.)
  # The slugs come from packaging/build-binary.py platform_slug().
  if Hardware::CPU.arm?
    url "https://github.com/Abhi-Subedi/LocalDrop/releases/download/v1.1.0/localdrop-1.1.0-macos-arm64.tar.gz"
    sha256 "8d7e15ba036790179b91aa3c0c22b44ef2e0d29140654bd258367dc67d53f2c7"
  else
    url "https://github.com/Abhi-Subedi/LocalDrop/releases/download/v1.1.0/localdrop-1.1.0-macos-x64.tar.gz"
    sha256 "c557db4472351c30404c08185febbf0dc0cf37178cc79df9a0d7b584a2d9bc27"
  end

  def install
    bin.install "localdrop"
    # AGPL-3.0 requires conveying the licence with the binary, so the tarballs
    # carry LICENSE (and a README) from 1.1.1 onward. Archives published before
    # that contain only the executable, and `pkgshare.install` on a missing file
    # aborts the whole install - so install them when they are there rather than
    # making an older-release user fail over a packaging nicety.
    %w[LICENSE README.md].each do |doc|
      pkgshare.install doc if File.exist?(doc)
    end
  end

  def caveats
    <<~EOS
      LocalDrop is a user-level daemon; Homebrew will not start it for you.

        localdrop              # start it (Ctrl-C to stop)
        localdrop install-service   # instead, run it at login via launchd

      It serves http://<your-lan-ip>:8080 and prints a first-run setup token.
      Files and the database live in ~/Library/Application Support/LocalDrop.

      Configuration: ~/Library/Application Support/LocalDrop/localdrop.env
      Full reference:  docs/CONFIGURATION.md in the repository.

      If you would rather use an existing PostgreSQL, set LOCALDROP_DATABASE_URL
      in that file; otherwise LocalDrop starts its own embedded cluster and you
      need no database at all.
    EOS
  end

  test do
    # --check proves the bundle is self-sufficient; it needs no database and
    # touches no data directory.
    output = shell_output("#{bin}/localdrop --check", 1)
    assert_match "LocalDrop #{version}", output
    assert_match "All checks passed", output
  end
end
