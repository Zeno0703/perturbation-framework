package org.instrumentation;

import net.bytebuddy.description.method.MethodDescription;
import net.bytebuddy.description.type.TypeDescription;
import net.bytebuddy.matcher.ElementMatcher;
import org.agent.AgentConfig;
import java.security.ProtectionDomain;
import static net.bytebuddy.matcher.ElementMatchers.nameContains;
import static net.bytebuddy.matcher.ElementMatchers.nameStartsWith;

class InstrumentationFilters {

    static ElementMatcher.Junction<net.bytebuddy.description.NamedElement> getIgnoreMatcher() {
        return nameStartsWith("net.bytebuddy.")
                .or(nameStartsWith("org.junit."))
                .or(nameStartsWith("org.apache.maven."))
                .or(nameStartsWith("java."))
                .or(nameStartsWith("javax."))
                .or(nameStartsWith("jdk."))
                .or(nameStartsWith("sun."))
                .or(nameStartsWith("org.probe."))
                .or(nameStartsWith("org.tracking."))
                .or(nameStartsWith("org.utils."))
                .or(nameStartsWith("org.instrumentation."))
                .or(nameStartsWith("org.agent."))
                .or(nameStartsWith("org.mockito"))
                .or(nameContains("MockitoMock"))
                .or(nameContains("EnhancerByCGLIB"))
                .or(nameContains("FastClassByCGLIB"))
                .or(nameStartsWith("org.jacoco"))
                .or(nameContains("$jacoco"));
    }

    static boolean isTargetType(TypeDescription typeDesc, ProtectionDomain pd) {
        if (typeDesc.isAnnotation()) return false;
        if (!AgentConfig.TARGET_PACKAGE.isEmpty() && !typeDesc.getName().startsWith(AgentConfig.TARGET_PACKAGE)) return false;
        return isProductionCode(pd);
    }

    static boolean isTargetMethod(MethodDescription method, TypeDescription type) {
        String name = method.getInternalName();
        if (method.isAbstract() || method.isNative() || method.isTypeInitializer()) return false;
        if (method.isSynthetic() || method.isBridge() || name.contains("$")) return false;
        if (type.isEnum() && (name.equals("values") || name.equals("valueOf"))) return false;
        return true;
    }

    private static boolean isProductionCode(ProtectionDomain pd) {
        if (pd == null || pd.getCodeSource() == null || pd.getCodeSource().getLocation() == null) return false;
        String loc = pd.getCodeSource().getLocation().toString();
        if (loc.contains("/target/test-classes") || loc.contains("\\target\\test-classes")) return false;
        return loc.contains("/target/classes") || loc.contains("\\target\\classes");
    }
}