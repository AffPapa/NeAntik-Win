TEST(NeAntikFingerprintTest, TimezoneRequiresSeed) {
  base::CommandLine command(base::CommandLine::NO_PROGRAM);
  command.AppendSwitchASCII(kTimeZoneSwitch, "Europe/Berlin");
  std::string error;
  EXPECT_FALSE(ParseFingerprintConfig(command, &error));
  EXPECT_FALSE(error.empty());
}

TEST(NeAntikFingerprintTest, RejectsMalformedTimezoneBeforeICU) {
  for (const char* zone : {"", "../Europe/Berlin", "Europe Berlin", "UTC\n",
                           "GMT+05:30", "Europe\\Berlin"}) {
    auto command = Seeded();
    command.AppendSwitchASCII(kTimeZoneSwitch, zone);
    std::string error;
    EXPECT_FALSE(ParseFingerprintConfig(command, &error)) << zone;
    EXPECT_FALSE(error.empty()) << zone;
  }
  auto command = Seeded();
  command.AppendSwitchASCII(kTimeZoneSwitch, std::string(129, 'A'));
  std::string error;
  EXPECT_FALSE(ParseFingerprintConfig(command, &error));
}

TEST(NeAntikFingerprintTest, ValidatesSystemIanaZonesAfterICUInitialization) {
  base::test::InitializeICUForTesting();
  for (const char* zone : {"UTC", "Europe/Berlin", "America/New_York",
                           "Asia/Kathmandu", "Etc/GMT+5"}) {
    auto command = Seeded();
    command.AppendSwitchASCII(kTimeZoneSwitch, zone);
    std::string error;
    auto config = ParseFingerprintConfig(command, &error);
    ASSERT_TRUE(config) << zone;
    EXPECT_TRUE(ValidateFingerprintTimeZone(*config, &error)) << zone;
    EXPECT_TRUE(error.empty()) << zone;
  }
}

TEST(NeAntikFingerprintTest, RejectsWellFormedUnknownTimezone) {
  base::test::InitializeICUForTesting();
  auto command = Seeded();
  command.AppendSwitchASCII(kTimeZoneSwitch, "Mars/Invisible");
  std::string error;
  auto config = ParseFingerprintConfig(command, &error);
  ASSERT_TRUE(config);
  EXPECT_FALSE(ValidateFingerprintTimeZone(*config, &error));
  EXPECT_FALSE(error.empty());
}
