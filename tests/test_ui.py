import tkinter as tk
import unittest
from unittest.mock import patch
from ultron.__main__ import App
from ultron.cloud import PRESETS


class UITests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        fake_config = {'provider': 'OpenAI', 'base_url': 'https://api.openai.com/v1',
                       'model': 'gpt-4.1-mini', 'key': '', 'remember': True,
                       'speech': True, 'tools': True, 'autolisten': True}
        self.settings_patcher = patch('ultron.__main__.settings.load', return_value=fake_config)
        self.settings_patcher.start()
        self.app = App(self.root, autostart=False)
        self.root.update()

    def tearDown(self):
        self.settings_patcher.stop()
        self.app.closing = True
        for timer in self.root.tk.call('after', 'info'):
            self.root.after_cancel(timer)
        self.root.destroy()

    def test_controls_fit_and_mute_remains_visible(self):
        for size in ('1360x860', '1160x760'):
            self.root.geometry(size)
            self.root.update()
            self.assertGreaterEqual(self.app.mute_button.winfo_height(), 34)
            self.assertGreaterEqual(self.app.hud.winfo_height(), 160)
            self.assertTrue(self.app.input.winfo_ismapped())
            self.assertLessEqual(self.app.mute_button.winfo_rooty()+self.app.mute_button.winfo_height(),
                                 self.root.winfo_rooty()+self.root.winfo_height())

    def test_switching_provider_clears_old_key(self):
        self.app.key.set('fake-openai-key')
        self.app.provider.set('NVIDIA Nemotron')
        self.app.change_provider()
        self.assertEqual(self.app.key.get(), '')
        self.assertEqual(self.app.endpoint.get(), PRESETS['NVIDIA Nemotron'][0])

    def test_connection_dialog_controls_are_accessible(self):
        self.app.open_settings()
        self.root.update()
        window = self.app.settings_window
        self.assertTrue(window.winfo_ismapped())
        self.assertTrue(self.app.test_button.winfo_ismapped())
        self.assertLessEqual(self.app.test_button.winfo_rooty()+self.app.test_button.winfo_height(),
                             window.winfo_rooty()+window.winfo_height())

    def test_failed_save_keeps_settings_visible(self):
        self.app.open_settings()
        self.root.update()
        with patch.object(self.app, 'apply', return_value=False):
            self.app.save_and_close()
        self.assertTrue(self.app.settings_window.winfo_ismapped())
        with patch.object(self.app, 'apply', return_value=True):
            self.app.save_and_close()
        self.root.update()
        self.assertFalse(self.app.settings_window.winfo_ismapped())

    def test_text_can_queue_while_voice_listener_runs(self):
        self.app.mode = 'voice'
        self.app.send('Open calculator')
        self.assertEqual(self.app.typed.get_nowait(), 'Open calculator')

    def test_quick_button_intent_survives_voice_queue(self):
        self.app.mode = 'voice'
        self.app.send('Open calculator', quick_app='calculator')
        job = self.app.typed.get_nowait()
        self.assertEqual(job, {'text': 'Open calculator', 'app': 'calculator'})
        with patch.object(self.app, 'respond') as respond:
            self.app.handle_command(job, 'text')
        respond.assert_called_once_with('Open calculator', quick_app='calculator')

    def test_quick_button_uses_local_action_without_provider_key(self):
        self.app.speech_enabled = False
        with patch.object(self.app.cloud, 'open_local_app', return_value='Requested opening calculator.') as local:
            with patch.object(self.app.cloud, 'reply') as remote:
                self.app.respond('Open calculator', quick_app='calculator')
        local.assert_called_once()
        remote.assert_not_called()

    def test_mute_cancels_pending_commands(self):
        self.app.want_listen = True
        self.app.typed.put('Open calculator')
        self.app.toggle_listening()
        self.assertFalse(self.app.want_listen)
        self.assertTrue(self.app.stop_event.is_set())
        self.assertTrue(self.app.typed.empty())

    def test_autostart_schedules_listener_without_button(self):
        self.app.closing = True
        for timer in self.root.tk.call('after', 'info'):
            self.root.after_cancel(timer)
        self.root.destroy()
        self.root = tk.Tk()
        from ultron import settings
        config = settings.load()
        config['autolisten'] = True
        with patch.object(App, 'start') as start, patch('ultron.__main__.settings.load', return_value=config):
            self.app = App(self.root, autostart=True)
            self.app.auto.set(True)
            self.root.after(850, self.root.quit)
            self.root.mainloop()
            start.assert_called_once()

