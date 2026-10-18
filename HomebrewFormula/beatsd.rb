# frozen_string_literal: true

# Homebrew formula for beatsd, the Beats ambient flow tracking daemon.
#
# This directory is the tap. Homebrew reads a tapped repo's
# HomebrewFormula/, so this repo is itself the tap lanterno/beats; as it is
# not named homebrew-<x>, users tap it by URL:
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
  version "0.9.1"
  license "MIT"

  on_macos do
    on_arm do
      url "https://github.com/lanterno/beats/releases/download/v#{version}/beatsd-darwin-arm64.tar.gz"
      sha256 "08472d23641f5ee586d3dd9561adf653cff788cb50a5647118ddf3263c20bf0d"
    end
    on_intel do
      url "https://github.com/lanterno/beats/releases/download/v#{version}/beatsd-darwin-amd64.tar.gz"
      sha256 "87c178dc06295e166b2c68bb71ae30b86bea4f80a84b8f6519bffba60b7b80ac"
    end
  end

  on_linux do
    on_arm do
      url "https://github.com/lanterno/beats/releases/download/v#{version}/beatsd-linux-arm64.tar.gz"
      sha256 "458d3d5a3ccf4451bfc9eb64656e7a9bcfbc2743e22e0dd2974120ac25145af5"
    end
    on_intel do
      url "https://github.com/lanterno/beats/releases/download/v#{version}/beatsd-linux-amd64.tar.gz"
      sha256 "01df62f7e390fac7eb754cc5169ed7e8d156c065957cc3e88d272ab67ffd9165"
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
