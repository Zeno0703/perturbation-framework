package org.instrumentation;

import net.bytebuddy.agent.builder.AgentBuilder;
import net.bytebuddy.dynamic.DynamicType;
import org.probe.PerturbationGate;

import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import java.util.List;

import static net.bytebuddy.matcher.ElementMatchers.nameStartsWith;

public class InstrumentationController {

    private static final String TARGET_PACKAGE = System.getProperty("perturb.package", "");

    public static void install(Instrumentation inst) {
        List<PerturbationStrategy> strategies = List.of(
                new ReturnPerturbationStrategy()
        );

        new AgentBuilder.Default()
                .with(AgentBuilder.RedefinitionStrategy.RETRANSFORMATION)
                .with(AgentBuilder.Listener.StreamWriting.toSystemError().withErrorsOnly())
                .with(AgentBuilder.Listener.StreamWriting.toSystemError().withTransformationsOnly())
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
                        .or(nameStartsWith("org.instrumentation."))
                        .or(nameStartsWith("org.agent.")))
                .type((typeDesc, classLoader, module, classBeingRedefined, pd) -> {
                    boolean isTargetClass = !TARGET_PACKAGE.isEmpty() ? typeDesc.getName().startsWith(TARGET_PACKAGE) : isLikelyProjectClass(pd);
                    return isTargetClass
                            && !typeDesc.isInterface()
                            && !typeDesc.isAnnotation()
                            && !typeDesc.isEnum();
                })
                .transform((builderInstance, type, loader, module, domain) -> {
                    DynamicType.Builder<?> modifiedBuilder = builderInstance;
                    for (PerturbationStrategy strategy : strategies) {
                        modifiedBuilder = strategy.apply(modifiedBuilder);
                    }
                    return modifiedBuilder;
                })
                .installOn(inst);
    }

    private static boolean isLikelyProjectClass(ProtectionDomain pd) {
        if (pd == null || pd.getCodeSource() == null || pd.getCodeSource().getLocation() == null) {
            System.out.println("False: Null ProtectionDomain or CodeSource");
            return false;
        }
        String loc = pd.getCodeSource().getLocation().toString();
        System.out.println("Location check: " + loc);

        return loc.contains("/target/classes") || loc.contains("/target/test-classes")
                || loc.contains("\\target\\classes") || loc.contains("\\target\\test-classes");
    }
}