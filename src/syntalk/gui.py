"""GTK 4 / libadwaita interface. The only module that imports gi."""

from __future__ import annotations

import threading

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")

from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from . import __version__  # noqa: E402
from .effects import EFFECTS, apply_text_rewrite, filter_chain  # noqa: E402
from .engine import Engine, EngineError  # noqa: E402
from .voices import Voice, discover, find  # noqa: E402

APP_ID = "nl.syntec.SynTalk"

_NO_EFFECT = "None"


class SynTalkWindow(Adw.ApplicationWindow):
    def __init__(self, application: Adw.Application) -> None:
        super().__init__(application=application, title="SynTalk")
        self.set_default_size(900, 620)

        self._engine = Engine()
        self._voices: list[Voice] = discover()
        self._playback = None
        self._rows: dict[Gtk.ListBoxRow, Voice] = {}

        self._toasts = Adw.ToastOverlay()
        self.set_content(self._toasts)

        if not self._voices:
            self._toasts.set_child(self._build_empty_state())
            return

        self._toasts.set_child(self._build_split_view())
        self._select_voice_key(self._voices[0].key)

    # ---------------------------------------------------------------- layout

    def _build_empty_state(self) -> Gtk.Widget:
        page = Adw.StatusPage(
            icon_name="audio-speakers-symbolic",
            title="No voices installed",
            description=(
                "SynTalk looks for Piper voice models in\n"
                "~/.local/share/piper-voices\n\n"
                "Download one with:\n"
                "~/.local/share/piper-venv/bin/python -m piper.download_voices "
                "--data-dir ~/.local/share/piper-voices en_US-lessac-high"
            ),
        )
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        view.set_content(page)
        return view

    def _build_split_view(self) -> Gtk.Widget:
        split = Adw.NavigationSplitView()
        split.set_sidebar(self._build_sidebar())
        split.set_content(self._build_content())
        return split

    def _build_sidebar(self) -> Adw.NavigationPage:
        self._list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self._list.add_css_class("navigation-sidebar")
        self._list.connect("row-selected", self._on_voice_selected)

        for index, voice in enumerate(self._voices):
            row = Adw.ActionRow(title=voice.display_name,
                                subtitle=voice.language_label)
            if voice.is_multi_speaker:
                badge = Gtk.Label(label=f"{voice.num_speakers}")
                badge.add_css_class("dim-label")
                badge.add_css_class("caption")
                row.add_suffix(badge)
            self._list.append(row)
            self._rows[self._list.get_row_at_index(index)] = voice

        scroller = Gtk.ScrolledWindow(child=self._list, vexpand=True)
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        view.set_content(scroller)
        return Adw.NavigationPage(child=view, title="Voices")

    def _build_content(self) -> Adw.NavigationPage:
        header = Adw.HeaderBar()
        save = Gtk.Button(icon_name="document-save-symbolic",
                          tooltip_text="Save as WAV")
        save.connect("clicked", self._on_save)
        header.pack_end(save)

        self._speaker_row = Adw.SpinRow.new_with_range(0, 0, 1)
        self._speaker_row.set_title("Speaker")
        self._speaker_group = Adw.PreferencesGroup()
        self._speaker_group.add(self._speaker_row)
        self._speaker_group.set_visible(False)

        self._buffer = Gtk.TextBuffer()
        text_view = Gtk.TextView(buffer=self._buffer,
                                 wrap_mode=Gtk.WrapMode.WORD_CHAR,
                                 top_margin=12, bottom_margin=12,
                                 left_margin=12, right_margin=12)
        text_view.add_css_class("card")
        scroller = Gtk.ScrolledWindow(child=text_view, vexpand=True)

        self._effect_names = [_NO_EFFECT, *sorted(EFFECTS)]
        self._effect_drop = Gtk.DropDown.new_from_strings(self._effect_names)
        self._effect_drop.connect("notify::selected", self._on_effect_changed)

        self._speed = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0.5, 2.0, 0.05)
        self._speed.set_value(1.0)
        self._speed.set_hexpand(True)
        self._speed.add_mark(1.0, Gtk.PositionType.BOTTOM, None)

        self._play = Gtk.Button()
        self._play.set_child(Adw.ButtonContent(label="Play",
                                               icon_name="media-playback-start-symbolic"))
        self._play.add_css_class("suggested-action")
        self._play.connect("clicked", self._on_play_clicked)

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        controls.append(Gtk.Label(label="Effect"))
        controls.append(self._effect_drop)
        controls.append(Gtk.Label(label="Speed"))
        controls.append(self._speed)
        controls.append(self._play)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                       margin_top=12, margin_bottom=12,
                       margin_start=12, margin_end=12)
        body.append(self._speaker_group)
        body.append(scroller)
        body.append(controls)

        view = Adw.ToolbarView()
        view.add_top_bar(header)
        view.set_content(body)

        shortcut = Gtk.ShortcutController()
        shortcut.add_shortcut(Gtk.Shortcut.new(
            Gtk.ShortcutTrigger.parse_string("<Control>Return"),
            Gtk.CallbackAction.new(self._on_shortcut_play),
        ))
        self.add_controller(shortcut)

        return Adw.NavigationPage(child=view, title="SynTalk")

    # ----------------------------------------------------------------- state

    def _selected_voice(self) -> Voice | None:
        return self._rows.get(self._list.get_selected_row())

    def _selected_effect(self):
        name = self._effect_names[self._effect_drop.get_selected()]
        return EFFECTS.get(name)

    def _select_voice_key(self, key: str) -> None:
        for row, voice in self._rows.items():
            if voice.key == key:
                self._list.select_row(row)
                return

    def _on_voice_selected(self, _list, row) -> None:
        voice = self._rows.get(row)
        if voice is None:
            return
        multi = voice.is_multi_speaker
        self._speaker_group.set_visible(multi)
        if multi:
            self._speaker_row.set_range(0, voice.num_speakers - 1)
            self._speaker_row.set_value(0)

    def _on_effect_changed(self, *_args) -> None:
        effect = self._selected_effect()
        if effect is None:
            return
        # Visible, undoable: the preset's own voice and speed are applied.
        self._select_voice_key(effect.voice_key)
        self._speed.set_value(effect.length_scale)

    def _text(self) -> str:
        start, end = self._buffer.get_bounds()
        return self._buffer.get_text(start, end, False)

    def _toast(self, message: str) -> None:
        self._toasts.add_toast(Adw.Toast(title=message, timeout=5))

    # --------------------------------------------------------------- actions

    def _on_shortcut_play(self, *_args) -> bool:
        self._on_play_clicked(self._play)
        return True

    def _on_play_clicked(self, _button) -> None:
        if self._playback is not None:
            # Playback.stop() blocks until both children are reaped (up to 10s
            # each on a hung ALSA device). Never run that on the UI thread.
            # The worker's playback.wait() returns once they die and drives
            # _playback_finished, which clears state and re-enables the button.
            self._play.set_sensitive(False)
            threading.Thread(target=self._playback.stop, daemon=True).start()
            return

        voice = self._selected_voice()
        text = self._text()
        if voice is None or not text.strip():
            return

        effect = self._selected_effect()
        speaker_id = (int(self._speaker_row.get_value())
                      if voice.is_multi_speaker else None)

        self._play.set_sensitive(False)
        threading.Thread(
            target=self._play_worker,
            args=(voice, text, self._speed.get_value(), speaker_id, effect),
            daemon=True,
        ).start()

    def _play_worker(self, voice, text, length_scale, speaker_id, effect) -> None:
        try:
            if effect is not None:
                text = apply_text_rewrite(effect, text)
            pcm = self._engine.synthesize(
                voice, text, length_scale=length_scale, speaker_id=speaker_id)
            chain = (filter_chain(effect, voice.sample_rate)
                     if effect is not None else None)
            playback = self._engine.play(pcm, voice.sample_rate, chain=chain)
        except EngineError as exc:
            GLib.idle_add(self._playback_failed, str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - never kill the worker silently
            GLib.idle_add(self._playback_failed, f"unexpected error: {exc}")
            return

        GLib.idle_add(self._playback_started, playback)
        playback.wait()
        GLib.idle_add(self._playback_finished)

    def _playback_started(self, playback) -> bool:
        self._playback = playback
        self._play.set_child(Adw.ButtonContent(
            label="Stop", icon_name="media-playback-stop-symbolic"))
        self._play.set_sensitive(True)
        return GLib.SOURCE_REMOVE

    def _playback_finished(self) -> bool:
        self._playback = None
        self._play.set_child(Adw.ButtonContent(
            label="Play", icon_name="media-playback-start-symbolic"))
        self._play.set_sensitive(True)
        return GLib.SOURCE_REMOVE

    def _playback_failed(self, message: str) -> bool:
        self._playback = None
        self._play.set_sensitive(True)
        self._toast(message)
        return GLib.SOURCE_REMOVE

    def _on_save(self, _button) -> None:
        voice = self._selected_voice()
        if voice is None or not self._text().strip():
            return
        dialog = Gtk.FileDialog(initial_name="syntalk.wav")
        dialog.save(self, None, self._on_save_chosen)

    def _on_save_chosen(self, dialog, result) -> None:
        try:
            gfile = dialog.save_finish(result)
        except GLib.Error:
            return  # user cancelled
        if gfile is None:
            return
        # Read every widget here, on the main loop. The worker must not touch GTK.
        voice = self._selected_voice()
        if voice is None:
            return
        args = (
            gfile.get_path(),
            voice,
            self._text(),
            self._selected_effect(),
            self._speed.get_value(),
            int(self._speaker_row.get_value()) if voice.is_multi_speaker else None,
        )
        threading.Thread(target=self._save_worker, args=args, daemon=True).start()

    def _save_worker(self, path, voice, text, effect, length_scale,
                     speaker_id) -> None:
        try:
            if effect is not None:
                text = apply_text_rewrite(effect, text)
            pcm = self._engine.synthesize(
                voice, text, length_scale=length_scale, speaker_id=speaker_id)
            chain = (filter_chain(effect, voice.sample_rate)
                     if effect is not None else None)
            self._engine.save_wav(pcm, voice.sample_rate, path, chain=chain)
        except Exception as exc:  # noqa: BLE001 - surfaced as a toast
            GLib.idle_add(self._toast, f"could not save: {exc}")
            return
        GLib.idle_add(self._toast, f"Saved {path}")


class SynTalkApp(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_activate(self) -> None:
        window = self.props.active_window or SynTalkWindow(self)
        window.present()
