package local.jiege.hook.gr;

import android.hardware.camera2.CaptureRequest;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedHelpers;
import local.jiege.hook.common.Log;

/** PLK110 GR 会话的 SDK／HAL 身份边界。 */
final class GrHalSession {
    private static final String TAG = "RicohGrPort";
    private static final String SDK = "com.oplus.ocs.camera.";
    private static final String CONFIGURE = "configure";
    private static final String PROFESSIONAL_MODE = "professional_mode";

    // 这两个 Key 属于 HAL CaptureRequest；缓存实例，避免每次请求阶段重复创建。
    private static final CaptureRequest.Key<Boolean> PREVIEW_HDR_SUPPORT =
        new CaptureRequest.Key<>("com.oplus.preview.hdr.support", Boolean.class);
    private static final CaptureRequest.Key<Boolean> CAPTURE_HDR_SUPPORT =
        new CaptureRequest.Key<>("com.oplus.capture.hdr.support", Boolean.class);

    private GrHalSession() {}

    static void install(ClassLoader classLoader) {
        final Class<?> grCapMode = XposedHelpers.findClass(SDK + "producer.mode.GRCapMode", classLoader);
        Class<?> professionalMode = XposedHelpers.findClass(SDK + "producer.mode.ProfessionalMode", classLoader);
        Class<?> builder = XposedHelpers.findClass(SDK + "metadata.parameter.PreviewParameter$Builder", classLoader);
        Class<?> requestTag = XposedHelpers.findClass(SDK + "common.util.CameraRequestTag", classLoader);
        final Object cameraModeKey = XposedHelpers.getStaticObjectField(
            XposedHelpers.findClass(SDK + "metadata.UConfigureKeys", classLoader), "KEY_CAMERA_MODE");

        XposedHelpers.findAndHookMethod(professionalMode, "updateStageParameterBuilder",
            builder, String.class, String.class, requestTag, new XC_MethodHook() {
                @Override protected void afterHookedMethod(MethodHookParam param) {
                    // 父方法失败时保留原异常；普通大师模式及其他模式不跨过这条 GR 边界。
                    if (param.hasThrowable() || !grCapMode.isInstance(param.thisObject)) return;
                    Object parameterBuilder = param.args[0];
                    XposedHelpers.callMethod(parameterBuilder, "set", PREVIEW_HDR_SUPPORT, Boolean.FALSE);
                    XposedHelpers.callMethod(parameterBuilder, "set", CAPTURE_HDR_SUPPORT, Boolean.FALSE);
                    if (CONFIGURE.equals(param.args[1])) {
                        XposedHelpers.callMethod(parameterBuilder, "set", cameraModeKey, PROFESSIONAL_MODE);
                        Log.i(TAG, "PLK110 GR uses master HAL tuning; SDK and APS remain GR");
                    }
                }
            });

        // getModeName、onConfigure 与 getSurfaceUseCase 保持 GRCapMode 原生实现。
        Log.i(TAG, "PLK110 native GR SDK session retained with HAL master boundary");
    }
}
