// Copyright 2026 The NeAntik Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "third_party/blink/public/common/fingerprinting/neantik_fingerprint.h"

#include <limits>
#include <string>

#include "base/command_line.h"
#include "testing/gtest/include/gtest/gtest.h"

namespace blink::neantik {
namespace {

base::CommandLine Seeded() {
  base::CommandLine command(base::CommandLine::NO_PROGRAM);
  command.AppendSwitchASCII(kSeedSwitch, "123456");
  return command;
}

TEST(NeAntikFingerprintTest, UnconfiguredIsExplicitlyDisabled) {
  base::CommandLine command(base::CommandLine::NO_PROGRAM);
  std::string error = "stale";
  EXPECT_FALSE(ParseFingerprintConfig(command, &error));
  EXPECT_TRUE(error.empty());
}

TEST(NeAntikFingerprintTest, DefaultsAreStableAndNotHostDerived) {
  auto command = Seeded();
  std::string error;
  auto config = ParseFingerprintConfig(command, &error);
  ASSERT_TRUE(config);
  EXPECT_EQ(config->seed, UINT64_C(123456));
  EXPECT_EQ(config->hardware_concurrency, 8u);
  EXPECT_EQ(config->device_memory, 8.0f);
  EXPECT_TRUE(error.empty());
}

TEST(NeAntikFingerprintTest, MaximumSeedAndExplicitHardware) {
  base::CommandLine command(base::CommandLine::NO_PROGRAM);
  command.AppendSwitchASCII(kSeedSwitch, "18446744073709551615");
  command.AppendSwitchASCII(kHardwareConcurrencySwitch, "16");
  command.AppendSwitchASCII(kDeviceMemorySwitch, "32");
  std::string error;
  auto config = ParseFingerprintConfig(command, &error);
  ASSERT_TRUE(config);
  EXPECT_EQ(config->seed, std::numeric_limits<uint64_t>::max());
  EXPECT_EQ(config->hardware_concurrency, 16u);
  EXPECT_EQ(config->device_memory, 32.0f);
}

TEST(NeAntikFingerprintTest, RejectsInvalidSeeds) {
  for (const char* value : {"", "0", "-1", "+1", " 1", "1 ", "1x",
                            "18446744073709551616"}) {
    base::CommandLine command(base::CommandLine::NO_PROGRAM);
    command.AppendSwitchASCII(kSeedSwitch, value);
    std::string error;
    EXPECT_FALSE(ParseFingerprintConfig(command, &error)) << value;
    EXPECT_FALSE(error.empty()) << value;
  }
}

TEST(NeAntikFingerprintTest, RejectsUnknownNeAntikFlags) {
  auto command = Seeded();
  command.AppendSwitchASCII("neantik-fingerprint-config", "unexpected.json");
  std::string error;
  EXPECT_FALSE(ParseFingerprintConfig(command, &error));
  EXPECT_FALSE(error.empty());
}

TEST(NeAntikFingerprintTest, RejectsOrphanHardwareOverrides) {
  for (const char* flag : {kHardwareConcurrencySwitch, kDeviceMemorySwitch}) {
    base::CommandLine command(base::CommandLine::NO_PROGRAM);
    command.AppendSwitchASCII(flag, "8");
    std::string error;
    EXPECT_FALSE(ParseFingerprintConfig(command, &error));
    EXPECT_FALSE(error.empty());
  }
}

TEST(NeAntikFingerprintTest, RejectsInvalidHardwareConcurrency) {
  for (const char* value : {"", "0", "65", "-1", "3.5", "99999999999999999999"}) {
    auto command = Seeded();
    command.AppendSwitchASCII(kHardwareConcurrencySwitch, value);
    std::string error;
    EXPECT_FALSE(ParseFingerprintConfig(command, &error));
    EXPECT_FALSE(error.empty());
  }
}

TEST(NeAntikFingerprintTest, AcceptsOnlyDiscreteMemoryValues) {
  for (const char* value : {"0.25", "0.5", "1", "2", "4", "8", "16", "32"}) {
    auto command = Seeded();
    command.AppendSwitchASCII(kDeviceMemorySwitch, value);
    std::string error;
    EXPECT_TRUE(ParseFingerprintConfig(command, &error)) << value;
    EXPECT_TRUE(error.empty()) << value;
  }
  for (const char* value : {"", "0", "3", "64", "NaN", "inf", "8.0", "-8"}) {
    auto command = Seeded();
    command.AppendSwitchASCII(kDeviceMemorySwitch, value);
    std::string error;
    EXPECT_FALSE(ParseFingerprintConfig(command, &error)) << value;
    EXPECT_FALSE(error.empty()) << value;
  }
}

TEST(NeAntikFingerprintTest, CoreInfoRequiresOutputPath) {
  base::CommandLine command(base::CommandLine::NO_PROGRAM);
  command.AppendSwitch(kCoreInfoSwitch);
  std::string error;
  EXPECT_FALSE(ParseFingerprintConfig(command, &error));
  EXPECT_FALSE(error.empty());
}

TEST(NeAntikFingerprintTest, MixingIsDeterministicAndDomainSeparated) {
  const uint64_t first = MixFingerprintSeed(123456, 0x43414e564153, 77);
  EXPECT_EQ(first, MixFingerprintSeed(123456, 0x43414e564153, 77));
  EXPECT_NE(first, MixFingerprintSeed(987654, 0x43414e564153, 77));
  EXPECT_NE(first, MixFingerprintSeed(123456, 0x415544494f, 77));
  EXPECT_NE(first, MixFingerprintSeed(123456, 0x43414e564153, 78));
}

}  // namespace
}  // namespace blink::neantik
