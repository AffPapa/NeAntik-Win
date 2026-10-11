TEST_F(RendererPreferencesUtilTest, NeAntikNativeExplicitProxyBlocksUdp) {
  base::CommandLine command(base::CommandLine::NO_PROGRAM);
  command.AppendSwitchASCII(switches::kProxyServer, "http://127.0.0.1:9999");
  blink::RendererPreferences values;
  values.webrtc_ip_handling_policy =
      blink::mojom::WebRtcIpHandlingPolicy::kDefault;
  values.webrtc_ip_handling_urls.push_back(
      {ContentSettingsPattern::FromString("[*.]example.com"),
       blink::mojom::WebRtcIpHandlingPolicy::kDefault});
  renderer_preferences_util::ApplyNeAntikProxiedWebRtcPolicy(
      &values, true, command);
  EXPECT_EQ(values.webrtc_ip_handling_policy,
            blink::mojom::WebRtcIpHandlingPolicy::kDisableNonProxiedUdp);
  EXPECT_TRUE(values.webrtc_ip_handling_urls.empty());
  EXPECT_EQ(pref_service_->GetString(prefs::kWebRTCIPHandlingPolicy), "default");
}

TEST_F(RendererPreferencesUtilTest, NeAntikOrdinaryProxyRemainsUnchanged) {
  base::CommandLine command(base::CommandLine::NO_PROGRAM);
  command.AppendSwitchASCII(switches::kProxyServer, "http://127.0.0.1:9999");
  blink::RendererPreferences values;
  values.webrtc_ip_handling_policy =
      blink::mojom::WebRtcIpHandlingPolicy::kDefaultPublicInterfaceOnly;
  values.webrtc_ip_handling_urls.push_back(
      {ContentSettingsPattern::FromString("[*.]example.com"),
       blink::mojom::WebRtcIpHandlingPolicy::kDefault});
  renderer_preferences_util::ApplyNeAntikProxiedWebRtcPolicy(
      &values, false, command);
  EXPECT_EQ(values.webrtc_ip_handling_policy,
            blink::mojom::WebRtcIpHandlingPolicy::kDefaultPublicInterfaceOnly);
  EXPECT_EQ(values.webrtc_ip_handling_urls.size(), 1u);
}

TEST_F(RendererPreferencesUtilTest, NeAntikNativeMissingOrEmptyProxyUnchanged) {
  for (bool empty_switch : {false, true}) {
    base::CommandLine command(base::CommandLine::NO_PROGRAM);
    if (empty_switch) {
      command.AppendSwitch(switches::kProxyServer);
    }
    blink::RendererPreferences values;
    values.webrtc_ip_handling_policy =
        blink::mojom::WebRtcIpHandlingPolicy::kDefault;
    values.webrtc_ip_handling_urls.push_back(
        {ContentSettingsPattern::FromString("[*.]example.com"),
         blink::mojom::WebRtcIpHandlingPolicy::kDefault});
    renderer_preferences_util::ApplyNeAntikProxiedWebRtcPolicy(
        &values, true, command);
    EXPECT_EQ(values.webrtc_ip_handling_policy,
              blink::mojom::WebRtcIpHandlingPolicy::kDefault);
    EXPECT_EQ(values.webrtc_ip_handling_urls.size(), 1u);
  }
}
