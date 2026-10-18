# frozen_string_literal: true

# Homebrew formula for beatsd, the Beats ambient flow tracking daemon.
#
# This file lives in the main beats repo as the canonical source. Copy it
# verbatim to a separate `homebrew-beats` tap repo (per the README.md
# beside it) under `Formula/beatsd.rb` to make
# `brew install lanterno/beats/beatsd` work.
#
# The PLACEHOLDER sha256 lines are filled in by hand (or with
# bump-formula-pr) from a release-daemon run: point the URLs at the new
# release tag and update the sha256s next to them.
class Beatsd < Formula
  desc "Ambient flow tracking daemon for Beats"
  homepage "https://github.com/lanterno/beats"
  version "0.1.0"
  license "MIT"

  on_macos do
    on_arm do
      url "https://github.com/lanterno/beats/releases/download/v#{version}/beatsd-darwin-arm64.tar.gz"
      sha256 "PLACEHOLDER_DARWIN_ARM64"
    end
    on_intel do
      url "https://github.com/lanterno/beats/releases/download/v#{version}/beatsd-darwin-amd64.tar.gz"
      sha256 "PLACEHOLDER_DARWIN_AMD64"
    end
  end

  on_linux do
    on_arm do
      url "https://github.com/lanterno/beats/releases/download/v#{version}/beatsd-linux-arm64.tar.gz"
      sha256 "PLACEHOLDER_LINUX_ARM64"
    end
    on_intel do
      url "https://github.com/lanterno/beats/releases/download/v#{version}/beatsd-linux-amd64.tar.gz"
      sha256 "PLACEHOLDER_LINUX_AMD64"
    end
  end

  def install
    bin.install "beatsd"
  end

  service do
    run [opt_bin/"beatsd", "run"]
    keep_alive true
    log_path var/"log/beatsd.log"
    error_log_path var/"log/beatsd.log"
  end

  test do
    assert_match "beatsd", shell_output("#{bin}/beatsd version")
  end
end
