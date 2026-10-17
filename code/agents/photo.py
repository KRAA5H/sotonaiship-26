"""Photo agent: structured features from a photo, in parallel with triage.

It starts the moment a photo arrives and runs on its own thread, so the
resident never waits for it: triage and the reply go ahead, and the features
are stored on the report when they are ready. The shape and the "never a
location" rule live in photo_features.py.
"""

import functools
from concurrent.futures import ThreadPoolExecutor

import llm
import photo_features

POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="agent")
PHOTO_TIMEOUT = 12


class PhotoAgent:
    name = "photo"

    def start(self, image):
        """A future for the features, or None when there is no photo."""
        if not image or not image[0]:
            return None
        return POOL.submit(self._analyse, image)

    @staticmethod
    def _analyse(image):
        chat = functools.partial(llm.chat, max_tokens=250, temperature=0.2,
                                 timeout=PHOTO_TIMEOUT, purpose="photo")
        return photo_features.analyse(image, chat=chat)

    @staticmethod
    def ready(future):
        """The features if the analysis has already finished, else None. Never waits."""
        if future is None or not future.done():
            return None
        try:
            return (future.result() or {}).get("features")
        except Exception:  # noqa: BLE001 - a failed analysis is just no features
            return None

    @staticmethod
    def when_done(future, callback):
        """Call callback(features) once the analysis finishes, if it found anything."""
        if future is None:
            return

        def done(f):
            try:
                features = (f.result() or {}).get("features")
            except Exception:  # noqa: BLE001
                return
            if features:
                callback(features)
        future.add_done_callback(done)
