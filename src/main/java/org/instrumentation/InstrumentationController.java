package org.instrumentation;

import net.bytebuddy.agent.builder.AgentBuilder;
import net.bytebuddy.description.type.TypeDescription;
import net.bytebuddy.dynamic.DynamicType;
import org.probe.PerturbationGate;
import org.probe.ProbeCatalog;

import java.lang.instrument.Instrumentation;
import java.util.List;
import java.util.Map;

public class InstrumentationController {

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
                .ignore(InstrumentationFilters.getIgnoreMatcher())
                .type((typeDesc, classLoader, module, classBeingRedefined, pd) ->
                        InstrumentationFilters.isTargetType(typeDesc, pd))
                .transform((builderInstance, type, loader, module, domain) -> {

                    registerProbesForType(type, loader);

                    DynamicType.Builder<?> modifiedBuilder = builderInstance;
                    for (PerturbationStrategy strategy : strategies) {
                        modifiedBuilder = strategy.apply(modifiedBuilder);
                    }
                    return modifiedBuilder;
                })
                .installOn(inst);
    }

    private static void registerProbesForType(TypeDescription type, ClassLoader loader) {
        String classResourcePath = type.getName().replace('.', '/') + ".class";

        Map<String, AsmMethodAnalyser.MethodLineInfo> classLineInfo = AsmMethodAnalyser.analyseClass(loader, classResourcePath);

        for (var method : type.getDeclaredMethods()) {
            if (!InstrumentationFilters.isTargetMethod(method, type)) continue;

            String locationKey = method.toString();
            String asmName = method.isConstructor() ? "<init>" : method.getInternalName();
            String asmDesc = method.getDescriptor();

            AsmMethodAnalyser.MethodLineInfo lineInfo = classLineInfo.getOrDefault(asmName + asmDesc, new AsmMethodAnalyser.MethodLineInfo());
            int methodFirstLine = lineInfo.firstLine != -1 ? lineInfo.firstLine : 0;

            TypeDescription.Generic retType = method.getReturnType();
            if (!retType.represents(void.class) && isSupportedType(retType)) {
                String typeName = resolveTypeName(retType);
                if (lineInfo.returnLines.isEmpty()) {
                    register(locationKey + ":return", "Modified " + typeName + " return value in " + locationKey, methodFirstLine);
                } else {
                    for (int retLine : lineInfo.returnLines) {
                        register(locationKey + ":return:" + retLine, "Modified " + typeName + " return on line " + retLine + " in " + locationKey, retLine);
                    }
                }
            }

            int argCount = method.getParameters().size();
            for (int i = 0; i < argCount; i++) {
                TypeDescription.Generic pType = method.getParameters().get(i).getType();
                if (isSupportedType(pType)) {
                    String typeName = resolveTypeName(pType);
                    register(locationKey + ":arg:" + i, "Modified " + typeName + " argument " + (i + 1) + " in " + locationKey, methodFirstLine);
                }
            }
        }
    }

    private static boolean isSupportedType(TypeDescription.Generic type) {
        return !type.represents(long.class) && !type.represents(float.class) && !type.represents(double.class);
    }

    private static void register(String key, String description, int line) {
        int id = ProbeCatalog.idForLocation(key);
        ProbeCatalog.describe(id, description);
        ProbeCatalog.setLine(id, line);
    }

    private static String resolveTypeName(TypeDescription.Generic type) {
        if (type.represents(int.class) || type.represents(short.class) || type.represents(byte.class) || type.represents(char.class)) return "Integer";
        if (type.represents(boolean.class)) return "boolean";
        return "Object";
    }
}