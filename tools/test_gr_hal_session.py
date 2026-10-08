"""编译真实 GR HAL Hook，以受控 SDK 对象验证会话身份边界。"""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parent.parent


class GrHalSessionTests(unittest.TestCase):
    def test_only_gr_requests_cross_the_hal_boundary(self):
        compiler = shutil.which("javac")
        runtime = shutil.which("java")
        self.assertIsNotNone(compiler, "GR HAL 会话测试需要 JDK")
        self.assertIsNotNone(runtime, "GR HAL 会话测试需要 JDK")

        sources = {
            "android/hardware/camera2/CaptureRequest.java": r'''package android.hardware.camera2;
import java.util.Objects;
public class CaptureRequest {
 public static final class Key<T> {
  private final String name;
  private final Class<T> type;
  public Key(String name, Class<T> type) { this.name = name; this.type = type; }
  public String getName() { return name; }
  @Override public boolean equals(Object value) {
   if (!(value instanceof Key)) return false;
   Key<?> other = (Key<?>) value;
   return name.equals(other.name) && type.equals(other.type);
  }
  @Override public int hashCode() { return Objects.hash(name, type); }
  @Override public String toString() { return name; }
 }
}''',
            "de/robv/android/xposed/XC_MethodHook.java": r'''package de.robv.android.xposed;
public abstract class XC_MethodHook {
 public static class MethodHookParam {
  public Object thisObject;
  public Object[] args;
  public Throwable throwable;
  public boolean hasThrowable() { return throwable != null; }
 }
 protected void afterHookedMethod(MethodHookParam param) throws Throwable {}
 public final void runAfter(MethodHookParam param) throws Throwable { afterHookedMethod(param); }
}''',
            "de/robv/android/xposed/XposedHelpers.java": r'''package de.robv.android.xposed;
import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.Arrays;
public class XposedHelpers {
 public static Class<?> hookedClass;
 public static String hookedName;
 public static Class<?>[] hookedParameters;
 public static XC_MethodHook hook;
 public static Class<?> findClass(String name, ClassLoader loader) {
  try { return Class.forName(name, true, loader); }
  catch (ClassNotFoundException e) { throw new AssertionError(e); }
 }
 public static Object getStaticObjectField(Class<?> type, String name) {
  try { Field field = type.getField(name); return field.get(null); }
  catch (ReflectiveOperationException e) { throw new AssertionError(e); }
 }
 public static Object findAndHookMethod(Class<?> type, String name, Object... signature) {
  if (signature.length != 5 || !(signature[4] instanceof XC_MethodHook)) throw new AssertionError();
  Class<?>[] parameters = Arrays.copyOf(signature, 4, Class[].class);
  try { type.getDeclaredMethod(name, parameters); }
  catch (NoSuchMethodException e) { throw new AssertionError("精确 SDK 签名不存在", e); }
  hookedClass = type;
  hookedName = name;
  hookedParameters = parameters;
  hook = (XC_MethodHook) signature[4];
  return null;
 }
 public static Object callMethod(Object target, String name, Object... args) {
  for (Method method : target.getClass().getMethods()) {
   Class<?>[] parameters = method.getParameterTypes();
   if (!method.getName().equals(name) || parameters.length != args.length) continue;
   boolean matches = true;
   for (int i = 0; i < args.length; i++) {
    if (args[i] != null && !parameters[i].isInstance(args[i])) matches = false;
   }
   if (!matches) continue;
   try { return method.invoke(target, args); }
   catch (IllegalAccessException e) { throw new AssertionError(e); }
   catch (InvocationTargetException e) { throw new RuntimeException(e.getCause()); }
  }
  throw new AssertionError("method not found: " + name);
 }
}''',
            "local/jiege/hook/common/Log.java": r'''package local.jiege.hook.common;
public class Log { public static void i(String tag, String message) {} }''',
            "com/oplus/ocs/camera/metadata/RequestKey.java": r'''package com.oplus.ocs.camera.metadata;
public class RequestKey<T> {
 private final String name;
 public RequestKey(String name) { this.name = name; }
 @Override public String toString() { return name; }
}''',
            "com/oplus/ocs/camera/metadata/UConfigureKeys.java": r'''package com.oplus.ocs.camera.metadata;
public class UConfigureKeys {
 public static final RequestKey<String> KEY_CAMERA_MODE = new RequestKey<>("camera_mode");
 public static final RequestKey<Boolean> PREVIEW_HDR_ENABLE = new RequestKey<>("preview_hdr_enable");
 public static final RequestKey<String> ULTRA_HDR_ENABLE = new RequestKey<>("ultra_hdr_enable");
 public static final RequestKey<String> OTHER = new RequestKey<>("other");
}''',
            "com/oplus/ocs/camera/metadata/parameter/PreviewParameter.java": r'''package com.oplus.ocs.camera.metadata.parameter;
import android.hardware.camera2.CaptureRequest;
import com.oplus.ocs.camera.metadata.RequestKey;
import java.util.LinkedHashMap;
import java.util.Map;
public class PreviewParameter {
 public static class Builder {
  public final Map<Object, Object> values = new LinkedHashMap<>();
  public <T> Builder set(CaptureRequest.Key<T> key, T value) { values.put(key, value); return this; }
  public <T> Builder set(RequestKey<T> key, T value) { values.put(key, value); return this; }
  public Object get(Object key) { return values.get(key); }
 }
}''',
            "com/oplus/ocs/camera/common/util/CameraRequestTag.java": r'''package com.oplus.ocs.camera.common.util;
public class CameraRequestTag {}''',
            "com/oplus/ocs/camera/producer/mode/ProfessionalMode.java": r'''package com.oplus.ocs.camera.producer.mode;
import com.oplus.ocs.camera.common.util.CameraRequestTag;
import com.oplus.ocs.camera.metadata.parameter.PreviewParameter;
public class ProfessionalMode {
 public void updateStageParameterBuilder(PreviewParameter.Builder builder, String stage,
                                         String cameraType, CameraRequestTag tag) {}
}''',
            "com/oplus/ocs/camera/producer/mode/GRCapMode.java": r'''package com.oplus.ocs.camera.producer.mode;
public class GRCapMode extends ProfessionalMode {}''',
            "com/oplus/ocs/camera/producer/mode/PhotoMode.java": r'''package com.oplus.ocs.camera.producer.mode;
public class PhotoMode {}''',
            "local/jiege/hook/gr/TestGrHalSession.java": r'''package local.jiege.hook.gr;
import android.hardware.camera2.CaptureRequest;
import com.oplus.ocs.camera.common.util.CameraRequestTag;
import com.oplus.ocs.camera.metadata.UConfigureKeys;
import com.oplus.ocs.camera.metadata.parameter.PreviewParameter;
import com.oplus.ocs.camera.producer.mode.GRCapMode;
import com.oplus.ocs.camera.producer.mode.PhotoMode;
import com.oplus.ocs.camera.producer.mode.ProfessionalMode;
import de.robv.android.xposed.XC_MethodHook.MethodHookParam;
import de.robv.android.xposed.XposedHelpers;
import java.util.LinkedHashMap;
import java.util.Map;
public class TestGrHalSession {
 private static final CaptureRequest.Key<Boolean> PREVIEW_HDR =
  new CaptureRequest.Key<>("com.oplus.preview.hdr.support", Boolean.class);
 private static final CaptureRequest.Key<Boolean> CAPTURE_HDR =
  new CaptureRequest.Key<>("com.oplus.capture.hdr.support", Boolean.class);
 private static void check(boolean result) { if (!result) throw new AssertionError(); }
 private static PreviewParameter.Builder builder() {
  PreviewParameter.Builder builder = new PreviewParameter.Builder();
  builder.set(PREVIEW_HDR, Boolean.TRUE);
  builder.set(CAPTURE_HDR, Boolean.TRUE);
  builder.set(UConfigureKeys.KEY_CAMERA_MODE, "gr_mode");
  builder.set(UConfigureKeys.PREVIEW_HDR_ENABLE, Boolean.TRUE);
  builder.set(UConfigureKeys.ULTRA_HDR_ENABLE, "on");
  builder.set(UConfigureKeys.OTHER, "keep");
  return builder;
 }
 private static void run(Object mode, PreviewParameter.Builder builder, String stage,
                         Throwable originalFailure) throws Throwable {
  MethodHookParam param = new MethodHookParam();
  param.thisObject = mode;
  param.args = new Object[] {builder, stage, "rear_sat", new CameraRequestTag()};
  param.throwable = originalFailure;
  XposedHelpers.hook.runAfter(param);
 }
 private static void checkSdkValues(PreviewParameter.Builder builder) {
  check(Boolean.TRUE.equals(builder.get(UConfigureKeys.PREVIEW_HDR_ENABLE)));
  check("on".equals(builder.get(UConfigureKeys.ULTRA_HDR_ENABLE)));
  check("keep".equals(builder.get(UConfigureKeys.OTHER)));
 }
 private static void checkUnchanged(Object mode) throws Throwable {
  PreviewParameter.Builder builder = builder();
  Map<Object, Object> before = new LinkedHashMap<>(builder.values);
  run(mode, builder, "configure", null);
  check(before.equals(builder.values));
 }
 private static void checkRequestStage(String stage) throws Throwable {
  PreviewParameter.Builder builder = builder();
  run(new GRCapMode(), builder, stage, null);
  check(Boolean.FALSE.equals(builder.get(PREVIEW_HDR)));
  check(Boolean.FALSE.equals(builder.get(CAPTURE_HDR)));
  check("gr_mode".equals(builder.get(UConfigureKeys.KEY_CAMERA_MODE)));
  checkSdkValues(builder);
 }
 public static void main(String[] args) throws Throwable {
  GrHalSession.install(TestGrHalSession.class.getClassLoader());
  check(XposedHelpers.hookedClass == ProfessionalMode.class);
  check("updateStageParameterBuilder".equals(XposedHelpers.hookedName));
  check(XposedHelpers.hookedParameters.length == 4);
  check(XposedHelpers.hookedParameters[0] == PreviewParameter.Builder.class);
  check(XposedHelpers.hookedParameters[1] == String.class);
  check(XposedHelpers.hookedParameters[2] == String.class);
  check(XposedHelpers.hookedParameters[3] == CameraRequestTag.class);

  checkUnchanged(new ProfessionalMode());
  checkUnchanged(new PhotoMode());
  checkRequestStage("start_preview");
  checkRequestStage("before_take_picture");

  PreviewParameter.Builder configured = builder();
  run(new GRCapMode(), configured, "configure", null);
  check(Boolean.FALSE.equals(configured.get(PREVIEW_HDR)));
  check(Boolean.FALSE.equals(configured.get(CAPTURE_HDR)));
  check("professional_mode".equals(configured.get(UConfigureKeys.KEY_CAMERA_MODE)));
  checkSdkValues(configured);

  PreviewParameter.Builder failed = builder();
  Map<Object, Object> beforeFailure = new LinkedHashMap<>(failed.values);
  RuntimeException failure = new RuntimeException("original method failed");
  run(new GRCapMode(), failed, "configure", failure);
  check(beforeFailure.equals(failed.values));
 }
}''',
        }

        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            for name, content in sources.items():
                path = work / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)

            production = PROJECT / "app/src/main/java/local/jiege/hook/gr/GrHalSession.java"
            subprocess.run(
                [
                    compiler,
                    "-d",
                    str(work),
                    str(production),
                    *(str(work / name) for name in sources),
                ],
                check=True,
            )
            subprocess.run(
                [runtime, "-cp", str(work), "local.jiege.hook.gr.TestGrHalSession"],
                check=True,
            )


if __name__ == "__main__":
    unittest.main()
