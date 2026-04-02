package org.instrumentation;

import net.bytebuddy.agent.builder.AgentBuilder;
import net.bytebuddy.dynamic.DynamicType;
import org.instrumentation.strategy.ArgumentPerturbationStrategy;
import org.instrumentation.strategy.PerturbationStrategy;
import org.instrumentation.strategy.ReturnPerturbationStrategy;
import org.instrumentation.strategy.VariablePerturbationStrategy;
import org.runtime.PerturbationGate;

import java.lang.instrument.Instrumentation;
import java.util.List;
import java.util.Map;

public class InstrumentationInstaller {

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
                .type((typeDesc, classLoader, module, classBeingRedefined, pd) -> InstrumentationFilters.isTargetType(typeDesc, pd))
                .transform((builderInstance, type, loader, module, domain) -> {
                    String classResourcePath = type.getName().replace('.', '/') + ".class";
                    Map<String, AsmMethodAnalyser.MethodLineInfo> lineInfoMap = AsmMethodAnalyser.analyseClass(loader, classResourcePath);

                    DynamicType.Builder<?> modifiedBuilder = builderInstance;
                    for (PerturbationStrategy strategy : strategies) {
                        modifiedBuilder = strategy.apply(modifiedBuilder, type, loader, lineInfoMap);
                    }

                    return modifiedBuilder;
                })
                .installOn(inst);
    }
}