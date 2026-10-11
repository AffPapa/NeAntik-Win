// Copyright 2026 The NeAntik Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef THIRD_PARTY_BLINK_PUBLIC_COMMON_FINGERPRINTING_NEANTIK_FINGERPRINT_H_
#define THIRD_PARTY_BLINK_PUBLIC_COMMON_FINGERPRINTING_NEANTIK_FINGERPRINT_H_

#include <cstdint>
#include <optional>
#include <string>

#include "third_party/blink/public/common/common_export.h"

namespace base {
class CommandLine;
}

namespace blink::neantik {

inline constexpr char kSeedSwitch[] = "neantik-fingerprint-seed";
inline constexpr char kHardwareConcurrencySwitch[] = "neantik-hardware-concurrency";
inline constexpr char kDeviceMemorySwitch[] = "neantik-device-memory";
inline constexpr char kCoreInfoSwitch[] = "neantik-core-info";
inline constexpr int kConfigSchema = 1;

struct BLINK_COMMON_EXPORT FingerprintConfig {
  uint64_t seed = 0;
  unsigned hardware_concurrency = 8;
  float device_memory = 8.0f;
};

// Missing seed returns nullopt with an empty error only when no other persona
// switches were supplied. A nonempty error is always a startup failure.
BLINK_COMMON_EXPORT std::optional<FingerprintConfig> ParseFingerprintConfig(
    const base::CommandLine& command_line,
    std::string* error);

// Immutable, thread-safe one-time snapshot. Window and all worker accessors use
// exactly this state. Invalid child state fails closed instead of using host data.
BLINK_COMMON_EXPORT const FingerprintConfig* GetFingerprintConfig();

// SplitMix64-style domain-separated integer mixing; specified unsigned arithmetic
// is identical across compilers/processes/threads. Not a cryptographic key.
BLINK_COMMON_EXPORT uint64_t MixFingerprintSeed(uint64_t seed,
                                               uint64_t domain,
                                               uint64_t value);

}  // namespace blink::neantik

#endif  // THIRD_PARTY_BLINK_PUBLIC_COMMON_FINGERPRINTING_NEANTIK_FINGERPRINT_H_
