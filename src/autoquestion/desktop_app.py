"""Native Windows window: closing it ends the local service and hotkeys."""
from ctypes import wintypes
import logging
from tempfile import TemporaryDirectory
import threading

from .app_icon import write_icon
from .desktop_instance import DesktopInstance, DesktopInstanceError
from .user_config import UserConfigStore
from .web_ui import ASSETS, UIController, UIServer


def main(*, store=None, controller=None, webview_module=None, test_driver=None, update_receipt=None):
    logging.basicConfig(level=logging.INFO, handlers=[logging.NullHandler()])
    renderer_logger = logging.getLogger('pywebview')
    renderer_logger.handlers = [logging.NullHandler()]
    renderer_logger.propagate = False
    store = UserConfigStore() if store is None else store
    with DesktopInstance(store.path) as instance:
        if not instance.primary:
            if not instance.reopen():
                raise DesktopInstanceError('AutoQuestion 正在启动或退出。请稍后再双击；不会重复启动答题服务。')
            return 0
        native_renderer = webview_module is None
        if native_renderer:
            import webview as webview_module
        controller = UIController(store=store) if controller is None else controller
        if controller.updater is None and test_driver is None and native_renderer:
            from .updates import UpdateManager
            controller.updater = UpdateManager()
        server = UIServer(controller)
        serving = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.1),
                                   name='autoquestion-desktop-http', daemon=False)
        serving.start()
        with TemporaryDirectory(prefix='autoquestion-window-') as directory:
            icon = ASSETS / 'AutoQuestion.ico'
            if not icon.is_file():
                icon = write_icon(directory)
            window = None
            try:
                window = webview_module.create_window('AutoQuestion', server.origin + '/#session=' + server.token,
                                                     width=1280, height=900, min_size=(980, 680),
                                                     text_select=True, confirm_close=False)
                window.events.closing += controller.begin_close
                window.events.closed += controller.begin_close
                if update_receipt is not None:
                    from .updates import notify_ready
                    window.events.loaded += lambda: notify_ready(update_receipt)
                server.exit_callback = window.destroy
                def focus():
                    window.restore()
                    window.show()
                    native = window.native
                    if native is not None:
                        user = instance.user
                        user.SetForegroundWindow.argtypes = [wintypes.HWND]
                        user.SetForegroundWindow(int(native.Handle.ToInt64()))
                instance.activate(focus)
                kwargs = dict(gui='edgechromium', debug=False, private_mode=True, icon=str(icon))
                if test_driver is None:
                    webview_module.start(**kwargs)
                else:
                    webview_module.start(lambda: test_driver(window, controller, server), **kwargs)
            finally:
                controller.begin_close()
                server.shutdown()
                serving.join()
                server.close()
    return 0
