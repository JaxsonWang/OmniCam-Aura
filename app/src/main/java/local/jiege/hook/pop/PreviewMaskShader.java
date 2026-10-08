package local.jiege.hook.pop;

import android.app.AndroidAppHelper;
import android.content.res.Resources;
import android.opengl.EGL14;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import local.jiege.hook.common.Log;
import local.jiege.hook.common.Symbols;

/** POP 的圆角过渡遮罩使用独立 shader，不应借用全局反色补光开关初始化。 */
public final class PreviewMaskShader {
    private static final String TAG = "PreviewMaskShader";

    private PreviewMaskShader() {}

    public static void install() throws ReflectiveOperationException {
        Symbols symbols = Symbols.get();
        Field mask = symbols.field("PreviewMask.shader");
        Constructor<?> constructor = mask.getType().getConstructor(int.class, int.class);
        XposedBridge.hookAllConstructors(symbols.cls("PreviewMask.canvas"), new XC_MethodHook() {
            @Override protected void afterHookedMethod(MethodHookParam param) throws Throwable {
                if (param.hasThrowable()) return;
                if (mask.get(param.thisObject) != null) {
                    Log.i(TAG, "kept native mask shader; inverse-light cache="
                        + symbols.get("InverseLight.supportCache", null));
                    return;
                }
                if (EGL14.EGL_NO_CONTEXT.equals(EGL14.eglGetCurrentContext())) {
                    throw new IllegalStateException("Preview mask initialization requires the canvas GL context");
                }
                Resources resources = AndroidAppHelper.currentApplication().getResources();
                int vertex = resources.getIdentifier("texture_vertex_shader_inverse_mask", "raw", "com.oplus.camera");
                int fragment = resources.getIdentifier("draw_inverse_mask_shader", "raw", "com.oplus.camera");
                if (vertex == 0 || fragment == 0) {
                    throw new IllegalStateException("Camera inverse-mask shader resources are missing");
                }
                Object shader = constructor.newInstance(vertex, fragment);
                if (!(Boolean) symbols.call("PreviewMask.shaderValid", shader)) {
                    throw new IllegalStateException("Camera inverse-mask shader failed to compile/link");
                }
                mask.set(param.thisObject, shader);
                Log.i(TAG, "initialized on " + Thread.currentThread().getName()
                    + "; inverse-light cache=" + symbols.get("InverseLight.supportCache", null));
            }
        });
        Log.i(TAG, "canvas constructor hook installed; inverse-light support is unchanged");
    }
}
