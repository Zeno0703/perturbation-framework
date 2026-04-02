package org.instrumentation;

import net.bytebuddy.description.method.MethodDescription;
import net.bytebuddy.description.type.TypeDescription;
import org.agent.AgentConfig;
import org.probe.ProbeCatalog;

import java.io.FileInputStream;
import java.io.InputStream;
import java.util.Properties;

public class ProbeRegistrar {

    private static final Properties signatureLines = new Properties();

    static {
        try (InputStream is = new FileInputStream(AgentConfig.OUT_DIR_STR + "/method_lines.properties")) {
            signatureLines.load(is);
        } catch (Exception ignored) {}
    }

    public static boolean isSupportedType(TypeDescription.Generic type) {
        return !type.represents(long.class) && !type.represents(float.class) &&
                !type.represents(double.class) && !type.represents(void.class);
    }

    public static String resolveTypeName(TypeDescription.Generic type) {
        if (type.represents(boolean.class)) return "boolean";
        if (type.represents(int.class) || type.represents(short.class) ||
                type.represents(byte.class) || type.represents(char.class)) return "Integer";
        return "Object";
    }

    public static String resolveTypeName(String asmDescriptor) {
        return switch (asmDescriptor) {
            case "Z" -> "boolean";
            case "I", "S", "B", "C" -> "Integer";
            default -> "Object";
        };
    }

    public static int getSignatureLine(TypeDescription type, MethodDescription method, int fallbackLine) {
        String asmName = method.isConstructor() ? "<init>" : method.getInternalName();
        StringBuilder paramSig = new StringBuilder();
        int argCount = method.getParameters().size();
        for (int i = 0; i < argCount; i++) {
            if (i > 0) paramSig.append(",");
            paramSig.append(method.getParameters().get(i).getType().asErasure().getSimpleName());
        }
        String lookupKey = type.getName() + "." + asmName + "." + paramSig.toString();

        if (signatureLines.containsKey(lookupKey)) {
            return Integer.parseInt(signatureLines.getProperty(lookupKey));
        }
        return fallbackLine;
    }

    private static int registerProbe(String key, String description, int line, String asmDesc) {
        int id = ProbeCatalog.idForLocation(key);
        ProbeCatalog.describe(id, description);
        ProbeCatalog.setDescriptor(id, asmDesc);
        if (line > 0) ProbeCatalog.setLine(id, line);
        return id;
    }

    public static int registerArgument(String locationKey, int argIndex, int line, String asmDesc, String typeName) {
        String key = locationKey + ":arg:" + argIndex;
        String desc = "Modified " + typeName + " argument " + (argIndex + 1) + " in " + locationKey;
        return registerProbe(key, desc, line, asmDesc);
    }

    public static int registerReturn(String locationKey, int line, String asmDesc, String typeName) {
        String key = line > 0 ? locationKey + ":return:" + line : locationKey + ":return";
        String desc = line > 0 ? "Modified " + typeName + " return on line " + line + " in " + locationKey
                : "Modified " + typeName + " return value in " + locationKey;
        return registerProbe(key, desc, line, asmDesc);
    }

    public static int registerVariable(String locationKey, int varIndex, int line, String asmDesc, String typeName, boolean isObject) {
        String key = locationKey + ":" + (isObject ? "objVar" : "var") + ":" + varIndex;
        String desc = "Modified " + typeName + " local variable (JVM slot " + varIndex + ") in " + locationKey;
        return registerProbe(key, desc, line, asmDesc);
    }

    public static void updateVariableDescription(int probeId, String locationKey, String varName, String typeName) {
        ProbeCatalog.describe(probeId, "Modified " + typeName + " local variable '" + varName + "' in " + locationKey);
    }
}