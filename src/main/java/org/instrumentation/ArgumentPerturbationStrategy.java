package org.instrumentation;

import net.bytebuddy.asm.Advice;
import net.bytebuddy.dynamic.DynamicType;
import net.bytebuddy.implementation.bytecode.assign.Assigner;
import org.probe.PerturbationGate;
import org.probe.ProbeCatalog;

import static net.bytebuddy.matcher.ElementMatchers.isMethod;
import static net.bytebuddy.matcher.ElementMatchers.not;
import static net.bytebuddy.matcher.ElementMatchers.isConstructor;
import static net.bytebuddy.matcher.ElementMatchers.isAbstract;
import static net.bytebuddy.matcher.ElementMatchers.isNative;

public class ArgumentPerturbationStrategy implements PerturbationStrategy {

    @Override
    public DynamicType.Builder<?> apply(DynamicType.Builder<?> builder) {
        return builder.visit(
                Advice.to(ArgumentAdvice.class).on(
                        isMethod()
                                .and(not(isConstructor()))
                                .and(not(isAbstract()))
                                .and(not(isNative()))
                )
        );
    }

    public static Object[] perturbArguments(Object[] args, String locationKey) {
        Object[] modifiedArgs = new Object[args.length];
        System.arraycopy(args, 0, modifiedArgs, 0, args.length);
        boolean writeBack = false;

        for (int i = 0; i < modifiedArgs.length; i++) {
            Object currentArg = modifiedArgs[i];
            if (currentArg == null) continue;

            String argKey = locationKey + ":arg:" + i;
            int probeId = ProbeCatalog.idForLocation(argKey);

            if (probeId != -1) {
                String typeName = "Object";
                if (currentArg instanceof Integer num) {
                    typeName = "Integer";
                    modifiedArgs[i] = PerturbationGate.apply(num.intValue(), probeId);
                } else if (currentArg instanceof Boolean bool) {
                    typeName = "boolean";
                    modifiedArgs[i] = PerturbationGate.apply(bool.booleanValue(), probeId);
                } else {
                    modifiedArgs[i] = PerturbationGate.apply(currentArg, probeId);
                }

                ProbeCatalog.describe(probeId, "Modified " + typeName + " argument at index " + i + " in " + locationKey);
                writeBack = true;
            }
        }

        return writeBack ? modifiedArgs : args;
    }

    public static class ArgumentAdvice {
        @Advice.OnMethodEnter
        public static void enter(
                @Advice.AllArguments(readOnly = false, typing = Assigner.Typing.DYNAMIC) Object[] args,
                @Advice.Origin String locationKey) {

            if (args != null && args.length > 0) {
                args = ArgumentPerturbationStrategy.perturbArguments(args, locationKey);
            }
        }
    }
}