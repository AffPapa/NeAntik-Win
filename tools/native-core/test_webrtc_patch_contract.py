"""Source-contract checks are not C++ compilation or network runtime proof."""
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('generator',Path(__file__).with_name('generate-webrtc-policy-patch.py'))
generator=importlib.util.module_from_spec(spec);spec.loader.exec_module(generator)

class WebRtcContractTests(unittest.TestCase):
    def setUp(self):
        self.patch=(generator.seed.PATCHES/'009-native-proxy-webrtc-policy.patch').read_text()
        self.added='\n'.join(line[1:] for line in self.patch.splitlines() if line.startswith('+') and not line.startswith('+++'))

    def test_trigger_is_native_and_nonempty_explicit_proxy_only(self):
        for required in ('!native_persona','!command_line.HasSwitch(switches::kProxyServer)',
                         'GetSwitchValueNative(switches::kProxyServer).empty()',
                         'blink::neantik::GetFingerprintConfig() != nullptr'):
            self.assertIn(required,self.added)
        self.assertIn('NeAntikOrdinaryProxyRemainsUnchanged',self.added)
        self.assertIn('NeAntikNativeMissingOrEmptyProxyUnchanged',self.added)

    def test_url_overrides_cannot_weaken_policy(self):
        self.assertIn('prefs->webrtc_ip_handling_urls.clear();',self.added)
        self.assertIn('kDisableNonProxiedUdp',self.added)
        self.assertIn('EXPECT_TRUE(values.webrtc_ip_handling_urls.empty())',self.added)

    def test_no_preferences_or_os_write_or_unreviewed_extension_hook(self):
        self.assertNotIn('pref_service->Set',self.added)
        self.assertNotIn('RegSetValue',self.added)
        self.assertNotIn('chrome_content_renderer_client',self.patch)
        self.assertNotIn('force-webrtc-ip-handling-policy',self.added)
        self.assertIn(generator.CAPABILITY,self.added)
        self.assertNotIn('webrtc_all_traffic_protected',self.added)

if __name__=='__main__':unittest.main()
