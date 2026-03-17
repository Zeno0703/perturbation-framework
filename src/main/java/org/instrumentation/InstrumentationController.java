package org.instrumentation;

import net.bytebuddy.agent.builder.AgentBuilder;
import net.bytebuddy.description.type.TypeDescription;
import net.bytebuddy.dynamic.DynamicType;
import org.probe.PerturbationGate;

import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import java.util.List;

import static net.bytebuddy.matcher.ElementMatchers.nameContains;
import static net.bytebuddy.matcher.ElementMatchers.nameStartsWith;

import net.bytebuddy.jar.asm.ClassReader;
import net.bytebuddy.jar.asm.ClassVisitor;
import net.bytebuddy.jar.asm.MethodVisitor;
import net.bytebuddy.jar.asm.Opcodes;

public class InstrumentationController {

    private static final String TARGET_PACKAGE = System.getProperty("perturb.package", "");

    public static void install(Instrumentation inst) {
        List<PerturbationStrategy> strategies = List.of(
                new ArgumentPerturbationStrategy(),
                new ReturnPerturbationStrategy(),
                new VariablePerturbationStrategy()
        );

        new AgentBuilder.Default()
                .with(AgentBuilder.RedefinitionStrategy.RETRANSFORMATION)
                .with(AgentBuilder.Listener.StreamWriting.toSystemError().withErrorsOnly())
                .assureReadEdgeTo(inst, PerturbationGate.class)
                .ignore(nameStartsWith("net.bytebuddy.")
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
                        .or(nameContains("$jacoco")))
                .type((typeDesc, classLoader, module, classBeingRedefined, pd) -> {
                    if (typeDesc.isInterface() || typeDesc.isAnnotation() || typeDesc.isEnum()) {
                        return false;
                    }

                    if (!TARGET_PACKAGE.isEmpty() && !typeDesc.getName().startsWith(TARGET_PACKAGE)) {
                        return false;
                    }

                    return isProductionCode(pd);
                })
                .transform((builderInstance, type, loader, module, domain) -> {

                    for (net.bytebuddy.description.method.MethodDescription.InDefinedShape method : type.getDeclaredMethods()) {
                        if (method.isConstructor() || method.isAbstract() || method.isNative() || method.isTypeInitializer()) continue;
                        if (method.isSynthetic() || method.isBridge() || method.getName().contains("$")) continue;
                        if (type.isEnum() && (method.getName().equals("values") || method.getName().equals("valueOf"))) continue;

                        String locationKey = method.toString();
                        int methodFirstLine = firstLineOf(loader, locationKey);

                        TypeDescription.Generic retType = method.getReturnType();
                        if (retType.represents(int.class) || retType.represents(short.class) || retType.represents(byte.class) || retType.represents(char.class)) {
                            int id = org.probe.ProbeCatalog.idForLocation(locationKey);
                            org.probe.ProbeCatalog.describe(id, "Modified Integer return value in " + locationKey);
                            org.probe.ProbeCatalog.setLine(id, methodFirstLine);
                        } else if (retType.represents(boolean.class)) {
                            int id = org.probe.ProbeCatalog.idForLocation(locationKey);
                            org.probe.ProbeCatalog.describe(id, "Modified boolean return value in " + locationKey);
                            org.probe.ProbeCatalog.setLine(id, methodFirstLine);
                        } else if (!retType.represents(void.class)) {
                            int id = org.probe.ProbeCatalog.idForLocation(locationKey);
                            org.probe.ProbeCatalog.describe(id, "Modified Object return value in " + locationKey);
                            org.probe.ProbeCatalog.setLine(id, methodFirstLine);
                        }

                        int argCount = method.getParameters().size();
                        for (int i = 0; i < argCount; i++) {
                            String argKey = locationKey + ":arg:" + i;
                            int id = org.probe.ProbeCatalog.idForLocation(argKey);

                            TypeDescription.Generic pType = method.getParameters().get(i).getType();
                            String typeName = "Object";
                            if (pType.represents(int.class) || pType.represents(short.class) || pType.represents(byte.class) || pType.represents(char.class)) {
                                typeName = "Integer";
                            } else if (pType.represents(boolean.class)) {
                                typeName = "boolean";
                            }

                            org.probe.ProbeCatalog.describe(id, "Modified " + typeName + " argument " + (i + 1) + " in " + locationKey);
                            org.probe.ProbeCatalog.setLine(id, methodFirstLine);
                        }
                    }

                    DynamicType.Builder<?> modifiedBuilder = builderInstance;
                    for (PerturbationStrategy strategy : strategies) {
                        modifiedBuilder = strategy.apply(modifiedBuilder);
                    }
                    return modifiedBuilder;
                })
                .installOn(inst);
    }

    private static boolean isProductionCode(ProtectionDomain pd) {
        if (pd == null || pd.getCodeSource() == null || pd.getCodeSource().getLocation() == null) {
            return false;
        }
        String loc = pd.getCodeSource().getLocation().toString();
        if (loc.contains("/target/test-classes") || loc.contains("\\target\\test-classes")) {
            return false;
        }
        return loc.contains("/target/classes") || loc.contains("\\target\\classes");
    }

    private static int firstLineOf(ClassLoader loader, String methodSignature) {
        if (loader == null) return -1;
        try {
            java.util.regex.Matcher m = java.util.regex.Pattern
                    .compile("([\\w\\.\\$]+)\\.[\\w\\$<>]+\\(")
                    .matcher(methodSignature);
            if (!m.find()) return -1;
            String resourcePath = m.group(1).replace('.', '/') + ".class";

            try (var stream = loader.getResourceAsStream(resourcePath)) {
                if (stream == null) return -1;
                int[] result = {-1};
                new ClassReader(stream).accept(new ClassVisitor(Opcodes.ASM9) {
                    @Override
                    public MethodVisitor visitMethod(int access, String name, String descriptor,
                                                     String signature, String[] exceptions) {
                        return new MethodVisitor(Opcodes.ASM9) {
                            @Override
                            public void visitLineNumber(int line, net.bytebuddy.jar.asm.Label start) {
                                if (result[0] == -1 && methodSignature.contains(name + "(")) {
                                    result[0] = line;
                                }
                            }
                        };
                    }
                }, ClassReader.SKIP_FRAMES);
                return result[0];
            }
        } catch (Exception e) {
            return -1;
        }
    }
}