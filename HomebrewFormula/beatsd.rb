# frozen_string_literal: true

# Homebrew formula for beatsd, the Beats ambient flow tracking daemon.
#
# This directory is the tap. Homebrew reads a tapped repo's
# HomebrewFormula/, so the beats repo itself is lanterno/beats; as the repo
# is not named homebrew-<x>, users tap it by URL:
#
#   brew tap lanterno/beats https://github.com/lanterno/beats
#   brew install beatsd
#
# On every release tag, .github/workflows/release-daemon.yml runs bump.sh
# beside this file, which rewrites the version line and the four sha256
# lines, and commits the result to main. Edit anything else freely in a
# pull request; bump.sh finds each sha256 on the line after the url that
# names its archive, so keep them paired.
class Beatsd < Formula
  desc "Ambient flow tracking daemon for Beats"
  homepage "https://github.com/lanterno/beats"
  version "0.9.0"
  license "MIT"

  on_macos do
    on_arm do
      url "https://github.com/lanterno/beats/releases/download/v#{version}/beatsd-darwin-arm64.tar.gz"
      sha256 "e9366f189e763251dbd818b287df67d6e3a1e22464818e94030e0fe64b751324"
    end
    on_intel do
      url "https://github.com/lanterno/beats/releases/download/v#{version}/beatsd-darwin-amd64.tar.gz"
      sha256 "a82fcc3ff7111001be004034a381a7f5b16c48169b740f3fa809ac54e1928dbd"
    end
  end

  on_linux do
    on_arm do
      url "https://github.com/lanterno/beats/releases/download/v#{version}/beatsd-linux-arm64.tar.gz"
      sha256 "efb469cb99a68193eb433c29c9db4b6da31fa7f2eccf5a6b409f13f8f7cc18b4"
    end
    on_intel do
      url "https://github.com/lanterno/beats/releases/download/v#{version}/beatsd-linux-amd64.tar.gz"
      sha256 "1e8b0eba50a38955111f4f4c75a6ccad89cc1244e713dac649544105f416723a"
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
    # The release build stamps the tag into the binary (-X main.version),
    # so this fails if the tarball is not the release the formula names.
    assert_match "beatsd v#{version}", shell_output("#{bin}/beatsd version")
  end
end
