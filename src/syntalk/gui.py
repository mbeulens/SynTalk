"""GTK 4 / libadwaita interface. The only module that imports gi."""

from __future__ import annotations

import sys
import threading
import time

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")

from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from .commandline import play_command, save_command  # noqa: E402
from .effects import EFFECTS, apply_text_rewrite, filter_chain  # noqa: E402
from .engine import Engine, EngineError  # noqa: E402
from .voices import Voice, discover  # noqa: E402

APP_ID = "nl.syntec.SynTalk"

_NO_EFFECT = "None"


class SynTalkWindow(Adw.ApplicationWindow):
    def __init__(self, application: Adw.Application) -> None:
        super().__init__(application=application, title="SynTalk")
        self.set_default_size(900, 620)

        self._engine = Engine()
        self._voices: list[Voice] = discover()
        self._playback = None
        self._busy = False
        self._saving = False
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
        # sys.executable is the absolute path of the interpreter actually
        # running this app, so the command works regardless of the working
        # directory it was launched from (e.g. the GNOME overview, whose
        # cwd is $HOME, not the project root).
        download_command = (
            f"{sys.executable} -m piper.download_voices "
            "--data-dir ~/.local/share/piper-voices en_US-lessac-high"
        )
        page = Adw.StatusPage(
            icon_name="audio-speakers-symbolic",
            title="No voices installed",
            description=(
                "SynTalk looks for Piper voice models in\n"
                "~/.local/share/piper-voices\n\n"
                "Download one with:\n"
                + download_command
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
        self._save_button = Gtk.Button(icon_name="document-save-symbolic",
                                       tooltip_text="Save as WAV")
        self._save_button.connect("clicked", self._on_save)
        header.pack_end(self._save_button)

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
        self._speed.set_tooltip_text("Higher is slower (Piper length scale)")

        self._play = Gtk.Button()
        self._play.set_child(Adw.ButtonContent(label="Play",
                                               icon_name="media-playback-start-symbolic"))
        self._play.add_css_class("suggested-action")
        self._play.connect("clicked", self._on_play_clicked)

        self._next_speaker = Gtk.Button()
        self._next_speaker.set_child(Adw.ButtonContent(
            label="Next speaker", icon_name="media-skip-forward-symbolic"))
        self._next_speaker.set_tooltip_text(
            "Select the next speaker and play the current text again")
        self._next_speaker.set_visible(False)
        self._next_speaker.connect("clicked", self._on_next_speaker_clicked)

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        controls.append(Gtk.Label(label="Effect"))
        controls.append(self._effect_drop)
        length_label = Gtk.Label(label="Length")
        length_label.set_tooltip_text("Higher is slower (Piper length scale)")
        controls.append(length_label)
        controls.append(self._speed)
        controls.append(self._next_speaker)
        controls.append(self._play)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                       margin_top=12, margin_bottom=12,
                       margin_start=12, margin_end=12)
        body.append(self._speaker_group)
        body.append(scroller)
        body.append(controls)
        body.append(self._build_log_pane())

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

    def _build_log_pane(self) -> Gtk.Widget:
        """Collapsible session log: every play/save and its equivalent
        shell command, plus failures. Collapsed by default so it never
        disturbs the layout above."""
        self._log_buffer = Gtk.TextBuffer()
        self._log_view = Gtk.TextView(
            buffer=self._log_buffer,
            editable=False,
            cursor_visible=False,
            monospace=True,
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
            top_margin=6, bottom_margin=6, left_margin=6, right_margin=6,
        )
        log_scroller = Gtk.ScrolledWindow(child=self._log_view)
        log_scroller.set_min_content_height(150)
        log_scroller.set_vexpand(False)

        copy_button = Gtk.Button(label="Copy")
        copy_button.connect("clicked", self._on_log_copy)
        clear_button = Gtk.Button(label="Clear")
        clear_button.connect("clicked", self._on_log_clear)

        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        toolbar.append(copy_button)
        toolbar.append(clear_button)

        log_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        log_box.append(toolbar)
        log_box.append(log_scroller)

        self._log_expander = Gtk.Expander(label="Log")
        self._log_expander.set_child(log_box)
        self._log_expander.set_expanded(False)
        return self._log_expander

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
        self._next_speaker.set_visible(multi)
        if multi:
            self._speaker_row.set_range(0, voice.num_speakers - 1)
            self._speaker_row.set_value(0)

    def _on_effect_changed(self, *_args) -> None:
        effect = self._selected_effect()
        if effect is None:
            return
        # The filter chain applies to whatever voice the user has selected;
        # an effect only ever touches the speed slider, never the sidebar.
        self._speed.set_value(effect.length_scale)

    def _text(self) -> str:
        start, end = self._buffer.get_bounds()
        return self._buffer.get_text(start, end, False)

    def _toast(self, message: str) -> None:
        self._toasts.add_toast(Adw.Toast(title=message, timeout=5))

    # ------------------------------------------------------------------- log

    def _format_log_entry(self, action: str, voice: Voice, text: str,
                          effect, *, command: str | None = None,
                          error: str | None = None) -> str:
        timestamp = time.strftime("%H:%M:%S")
        effect_name = effect.name if effect is not None else "none"
        lines = [f"[{timestamp}] {action} · {voice.key} · {effect_name}",
                 f"  text: {text}"]
        if command is not None:
            lines.append(f"  $ {command}")
        if error is not None:
            lines.append(f"  ! {error}")
        return "\n".join(lines) + "\n"

    def _log(self, entry: str) -> None:
        # Callable from a worker thread: GLib.idle_add is thread-safe and
        # merely schedules the real insert on the main loop below. The
        # worker itself never touches self._log_buffer directly.
        GLib.idle_add(self._append_log_entry, entry)

    def _append_log_entry(self, entry: str) -> bool:
        self._log_buffer.insert(self._log_buffer.get_end_iter(), entry)
        end = self._log_buffer.get_end_iter()
        self._log_view.scroll_to_iter(end, 0.0, False, 0.0, 0.0)
        return GLib.SOURCE_REMOVE

    def _on_log_copy(self, _button) -> None:
        start, end = self._log_buffer.get_bounds()
        text = self._log_buffer.get_text(start, end, False)
        self.get_clipboard().set(text)

    def _on_log_clear(self, _button) -> None:
        self._log_buffer.set_text("", -1)

    # --------------------------------------------------------------- actions

    def _on_shortcut_play(self, *_args) -> bool:
        self._on_play_clicked(self._play)
        return True

    def _on_play_clicked(self, _button) -> None:
        # _busy is the single source of truth for "a worker is in flight" —
        # unlike button sensitivity, a Gtk.ShortcutController does not
        # consult it, so Ctrl+Return during synthesis must check it too.
        if self._busy:
            return
        if self._playback is not None:
            # Playback.stop() blocks until both children are reaped (up to 10s
            # each on a hung ALSA device). Never run that on the UI thread.
            # The worker's playback.wait() returns once they die and drives
            # _playback_finished, which clears _busy and restores the button.
            self._busy = True
            self._play.set_sensitive(False)
            threading.Thread(target=self._playback.stop, daemon=True).start()
            return
        self._start_playback()

    def _on_next_speaker_clicked(self, _button) -> None:
        if self._busy or self._playback is not None:
            return
        voice = self._selected_voice()
        if voice is None or not voice.is_multi_speaker:
            return
        if not self._text().strip():
            return
        next_id = (int(self._speaker_row.get_value()) + 1) % voice.num_speakers
        self._speaker_row.set_value(next_id)
        self._start_playback(action="next-speaker")

    def _start_playback(self, *, action: str = "play") -> None:
        """Gather every widget value on the main loop, mark busy, and hand
        off to a worker thread. Shared by Play and Next-speaker so the two
        entry points can never diverge."""
        voice = self._selected_voice()
        text = self._text()
        if voice is None or not text.strip():
            return

        effect = self._selected_effect()
        speaker_id = (int(self._speaker_row.get_value())
                      if voice.is_multi_speaker else None)

        self._busy = True
        self._play.set_sensitive(False)
        self._next_speaker.set_sensitive(False)
        threading.Thread(
            target=self._play_worker,
            args=(voice, text, self._speed.get_value(), speaker_id, effect,
                  action),
            daemon=True,
        ).start()

    def _play_worker(self, voice, text, length_scale, speaker_id, effect,
                     action="play") -> None:
        spoken_text = text
        try:
            if effect is not None:
                spoken_text = apply_text_rewrite(effect, text)
            chain = (filter_chain(effect, voice.sample_rate)
                     if effect is not None else None)
            # Every input to the command is known before speaking starts,
            # so log it immediately rather than waiting on synthesis.
            command = play_command(
                voice, spoken_text, length_scale=length_scale,
                speaker_id=speaker_id, chain=chain)
            playback = self._engine.speak(
                voice, spoken_text, length_scale=length_scale,
                speaker_id=speaker_id, chain=chain)
        except EngineError as exc:
            self._log(self._format_log_entry(
                action, voice, text, effect, error=str(exc)))
            GLib.idle_add(self._playback_failed, str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - never kill the worker silently
            self._log(self._format_log_entry(
                action, voice, text, effect, error=f"unexpected error: {exc}"))
            GLib.idle_add(self._playback_failed, f"unexpected error: {exc}")
            return

        self._log(self._format_log_entry(
            action, voice, spoken_text, effect, command=command))
        GLib.idle_add(self._playback_started, playback)
        playback.wait()
        if playback.error is not None:
            message = str(playback.error)
            self._log(self._format_log_entry(
                action, voice, spoken_text, effect, error=message))
            GLib.idle_add(self._playback_failed, message)
        else:
            GLib.idle_add(self._playback_finished)

    def _set_play_button(self, label: str, icon_name: str) -> None:
        self._play.set_child(Adw.ButtonContent(label=label, icon_name=icon_name))

    def _playback_started(self, playback) -> bool:
        self._playback = playback
        self._busy = False
        self._set_play_button("Stop", "media-playback-stop-symbolic")
        self._play.set_sensitive(True)
        # Next-speaker stays insensitive for the whole playback, not just
        # the busy window: it would otherwise let a second worker start
        # while the first is still audible.
        return GLib.SOURCE_REMOVE

    def _playback_finished(self) -> bool:
        self._playback = None
        self._busy = False
        self._set_play_button("Play", "media-playback-start-symbolic")
        self._play.set_sensitive(True)
        self._next_speaker.set_sensitive(True)
        return GLib.SOURCE_REMOVE

    def _playback_failed(self, message: str) -> bool:
        self._playback = None
        self._busy = False
        self._set_play_button("Play", "media-playback-start-symbolic")
        self._play.set_sensitive(True)
        self._next_speaker.set_sensitive(True)
        self._toast(message)
        return GLib.SOURCE_REMOVE

    def _on_save(self, _button) -> None:
        # self._saving guards the same race the design note on _busy
        # describes for playback: without it, a save that takes ~15s looks
        # like a missed click, the user clicks Save again, picks the same
        # path, and two ffmpeg -y processes race on one file.
        if self._saving:
            return
        voice = self._selected_voice()
        if voice is None or not self._text().strip():
            return
        self._saving = True
        self._save_button.set_sensitive(False)
        dialog = Gtk.FileDialog(initial_name="syntalk.wav")
        dialog.save(self, None, self._on_save_chosen)

    def _on_save_chosen(self, dialog, result) -> None:
        try:
            gfile = dialog.save_finish(result)
        except GLib.Error:
            self._saving = False
            self._save_button.set_sensitive(True)
            return  # user cancelled
        if gfile is None:
            self._saving = False
            self._save_button.set_sensitive(True)
            return
        # Read every widget here, on the main loop. The worker must not touch GTK.
        voice = self._selected_voice()
        if voice is None:
            self._saving = False
            self._save_button.set_sensitive(True)
            return
        path = gfile.get_path()
        args = (
            path,
            voice,
            self._text(),
            self._selected_effect(),
            self._speed.get_value(),
            int(self._speaker_row.get_value()) if voice.is_multi_speaker else None,
        )
        # Feedback at the START of the save is what the double-click bug is
        # missing: the absent "something is happening" cue is exactly what
        # makes a slow save look like a missed click.
        self._toast(f"Saving {path}…")
        threading.Thread(target=self._save_worker, args=args, daemon=True).start()

    def _save_worker(self, path, voice, text, effect, length_scale,
                     speaker_id) -> None:
        spoken_text = text
        try:
            if effect is not None:
                spoken_text = apply_text_rewrite(effect, text)
            pcm = self._engine.synthesize(
                voice, spoken_text, length_scale=length_scale, speaker_id=speaker_id)
            chain = (filter_chain(effect, voice.sample_rate)
                     if effect is not None else None)
            command = save_command(
                voice, spoken_text, path, length_scale=length_scale,
                speaker_id=speaker_id, chain=chain)
            self._engine.save_wav(pcm, voice.sample_rate, path, chain=chain)
        except Exception as exc:  # noqa: BLE001 - surfaced as a toast
            self._log(self._format_log_entry(
                "save", voice, text, effect, error=str(exc)))
            GLib.idle_add(self._save_finished, f"could not save: {exc}")
            return
        self._log(self._format_log_entry(
            "save", voice, spoken_text, effect, command=command))
        GLib.idle_add(self._save_finished, f"Saved {path}")

    def _save_finished(self, message: str) -> bool:
        self._saving = False
        self._save_button.set_sensitive(True)
        self._toast(message)
        return GLib.SOURCE_REMOVE


class SynTalkApp(Adw.Application):
    def __init__(self) -> None:
        # GTK derives WM_CLASS from the program name, not the application id.
        # Setting it here keeps StartupWMClass in the .desktop entry matching
        # the real running window, so GNOME can associate the two for
        # taskbar grouping / "focus existing window".
        GLib.set_prgname(APP_ID)
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_activate(self) -> None:
        window = self.props.active_window or SynTalkWindow(self)
        window.present()
