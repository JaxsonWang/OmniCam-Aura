package local.omnicam.aura;

import android.os.Build;

/** 与模块的机型配置保持一致，固件更新后禁止继续使用旧的原生布局。 */
final class SupportedDevice {
    private SupportedDevice() {}

    static boolean matches(String model, String firmware) {
        return "PMA110".equals(model)
            || ("PLK110".equals(model) && "PLK110_17.0.0.102(CN01)".equals(firmware));
    }

    static boolean current() {
        return matches(Build.MODEL, Build.DISPLAY);
    }
}
