package local.jiege.hook.common;

import java.lang.reflect.Field;
import java.lang.reflect.Modifier;

/** Lookups into the obfuscated camera and gallery code that do not rely on member names. */
public final class Reflection {
    private static final String DATA_KEY = "com.oplus.camera.data.DataKey";

    private Reflection() {}

    /** True if any instance String field of {@code object} (or a superclass) equals {@code value}. */
    public static boolean hasStringField(Object object, String value) throws IllegalAccessException {
        for (Class<?> type = object.getClass(); type != null; type = type.getSuperclass()) {
            for (Field field : type.getDeclaredFields()) {
                if (field.getType() == String.class && !Modifier.isStatic(field.getModifiers())) {
                    field.setAccessible(true);
                    if (value.equals(field.get(object))) return true;
                }
            }
        }
        return false;
    }

    /**
     * Finds the camera's DataKey constant for a preference name. The key holders (m9.d, m9.e, ...)
     * are obfuscated, but each DataKey keeps its preference name in a String field.
     */
    public static Object findDataKey(Class<?> holder, String preferenceName) throws IllegalAccessException {
        for (Field field : holder.getDeclaredFields()) {
            // Holders also keep feature keys (com.oplus.ocs...FeatureKey) under the same names.
            if (!Modifier.isStatic(field.getModifiers()) || !DATA_KEY.equals(field.getType().getName())) continue;
            field.setAccessible(true);
            Object key = field.get(null);
            if (key != null && hasStringField(key, preferenceName)) return key;
        }
        throw new IllegalStateException("DataKey not found: " + preferenceName);
    }

    /** First non-null instance field whose declared type has the given class name. */
    public static Object findFieldByType(Object object, String typeName) throws IllegalAccessException {
        if (object == null) return null;
        for (Class<?> type = object.getClass(); type != null; type = type.getSuperclass()) {
            for (Field field : type.getDeclaredFields()) {
                if (Modifier.isStatic(field.getModifiers()) || !typeName.equals(field.getType().getName())) continue;
                field.setAccessible(true);
                Object value = field.get(object);
                if (value != null) return value;
            }
        }
        return null;
    }
}
