"""Doctor 私有子进程：无网络的 headless Chromium 检查，退出即清理。"""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import sys


def contain_process_tree():
    """Windows Job 在子进程结束/被超时终止时回收其 Chromium/driver 后代。"""
    if sys.platform != 'win32':
        raise RuntimeError('Windows-only runtime check')
    size = ctypes.c_size_t
    class Basic(ctypes.Structure):
        _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64),
                    ('flags', wintypes.DWORD), ('min_ws', size), ('max_ws', size),
                    ('active_limit', wintypes.DWORD), ('affinity', size),
                    ('priority', wintypes.DWORD), ('scheduling', wintypes.DWORD)]
    class IO(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in ('read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes')]
    class Extended(ctypes.Structure):
        _fields_ = [('basic', Basic), ('io', IO), ('process_memory', size), ('job_memory', size),
                    ('peak_process_memory', size), ('peak_job_memory', size)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    job = kernel.CreateJobObjectW(None, None)
    limits = Extended()
    limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not job or not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
        if job:
            kernel.CloseHandle(job)
        raise RuntimeError('Cannot contain runtime probe')
    if not kernel.AssignProcessToJobObject(job, kernel.GetCurrentProcess()):
        kernel.CloseHandle(job)
        raise RuntimeError('Cannot contain runtime probe')
    # 不提前 CloseHandle：Job 包含当前子进程，句柄由 OS 在退出时关闭。
    return job


def main():
    result = {'ok': False}
    try:
        job = contain_process_tree()
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            if not Path(playwright.chromium.executable_path).is_file():
                raise RuntimeError('Runtime missing')
            browser = playwright.chromium.launch(headless=True, timeout=15000,
                args=['--disable-background-networking', '--disable-component-update', '--no-first-run'])
            try:
                context = browser.new_context(service_workers='block', accept_downloads=False)
                context.route('**/*', lambda route: route.abort())
                page = context.new_page()  # about:blank；无 URL 导航或截图。
                result['ok'] = page.evaluate('document.readyState') == 'complete'
            finally:
                browser.close()
    except Exception:
        result['ok'] = False  # 包括关闭失败；不输出原始异常。
    print(json.dumps(result), flush=True)
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
