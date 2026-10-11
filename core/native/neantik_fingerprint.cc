// Copyright 2026 The NeAntik Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "third_party/blink/public/common/fingerprinting/neantik_fingerprint.h"

#include <array>
#include <string_view>
#include <utility>

#include "base/check.h"
#include "base/command_line.h"
#include "base/strings/string_number_conversions.h"
#include "base/strings/string_util.h"

namespace blink::neantik {
namespace {

bool IsDecimal(std::string_view value) {
  if (value.empty() || value.size() > 20) {
    return false;
  }
  for (char c : value) {
    if (c < '0' || c > '9') {
      return false;
    }
  }
  return true;
}

}  // namespace

std::optional<FingerprintConfig> ParseFingerprintConfig(
    const base::CommandLine& command_line,
    std::string* error) {
  CHECK(error);
  error->clear();
  for (const auto& [name, ignored_value] : command_line.GetSwitches()) {
    if (base::StartsWith(name, "neantik-", base::CompareCase::SENSITIVE) &&
        name != kSeedSwitch && name != kHardwareConcurrencySwitch &&
        name != kDeviceMemorySwitch && name != kCoreInfoSwitch) {
      *error = "Unknown NeAntik switch";
      return std::nullopt;
    }
  }
  if (command_line.HasSwitch(kCoreInfoSwitch) &&
      command_line.GetSwitchValuePath(kCoreInfoSwitch).empty()) {
    *error = "NeAntik core-info requires an output path";
    return std::nullopt;
  }
  if (!command_line.HasSwitch(kSeedSwitch)) {
    if (command_line.HasSwitch(kHardwareConcurrencySwitch) ||
        command_line.HasSwitch(kDeviceMemorySwitch)) {
      *error = "NeAntik hardware overrides require a fingerprint seed";
    }
    return std::nullopt;
  }
  FingerprintConfig config;
  const std::string seed = command_line.GetSwitchValueASCII(kSeedSwitch);
  if (!IsDecimal(seed) || !base::StringToUint64(seed, &config.seed) ||
      config.seed == 0) {
    *error = "NeAntik fingerprint seed must be a nonzero uint64 decimal";
    return std::nullopt;
  }
  if (command_line.HasSwitch(kHardwareConcurrencySwitch)) {
    const std::string cpu =
        command_line.GetSwitchValueASCII(kHardwareConcurrencySwitch);
    if (!IsDecimal(cpu) ||
        !base::StringToUint(cpu, &config.hardware_concurrency) ||
        config.hardware_concurrency < 1 || config.hardware_concurrency > 64) {
      *error = "NeAntik hardware concurrency must be in [1,64]";
      return std::nullopt;
    }
  }
  if (command_line.HasSwitch(kDeviceMemorySwitch)) {
    const std::string memory =
        command_line.GetSwitchValueASCII(kDeviceMemorySwitch);
    constexpr std::array<std::pair<std::string_view, float>, 8> kValues = {{
        {"0.25", 0.25f}, {"0.5", 0.5f}, {"1", 1.0f}, {"2", 2.0f},
        {"4", 4.0f}, {"8", 8.0f}, {"16", 16.0f}, {"32", 32.0f}}};
    bool valid = false;
    for (const auto& [text, value] : kValues) {
      if (memory == text) {
        config.device_memory = value;
        valid = true;
        break;
      }
    }
    if (!valid) {
      *error = "NeAntik device memory must be one of 0.25,0.5,1,2,4,8,16,32";
      return std::nullopt;
    }
  }
  return config;
}

const FingerprintConfig* GetFingerprintConfig() {
  static const std::optional<FingerprintConfig> config = [] {
    std::string error;
    auto parsed = ParseFingerprintConfig(
        *base::CommandLine::ForCurrentProcess(), &error);
    CHECK(error.empty()) << error;
    return parsed;
  }();
  return config.has_value() ? &config.value() : nullptr;
}

uint64_t MixFingerprintSeed(uint64_t seed, uint64_t domain, uint64_t value) {
  uint64_t mixed = seed ^ domain ^ (value + UINT64_C(0x9e3779b97f4a7c15));
  mixed = (mixed ^ (mixed >> 30)) * UINT64_C(0xbf58476d1ce4e5b9);
  mixed = (mixed ^ (mixed >> 27)) * UINT64_C(0x94d049bb133111eb);
  return mixed ^ (mixed >> 31);
}

}  // namespace blink::neantik
