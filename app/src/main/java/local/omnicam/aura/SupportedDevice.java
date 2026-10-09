package local.omnicam.aura;

import android.os.Build;

/** 与模块共用系统分支策略，同分支补丁更新继续由具体 Hook 合同判断。 */
final class SupportedDevice {
    private SupportedDevice() {}

    static boolean matches(String model, String firmware, int sdk) {
        return DevicePolicy.matches(model, firmware, sdk);
    }

    static boolean current() {
        return matches(Build.MODEL, Build.DISPLAY, Build.VERSION.SDK_INT);
    }
}
