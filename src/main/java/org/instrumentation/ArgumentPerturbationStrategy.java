package org.instrumentation;

import net.bytebuddy.asm.Advice;
import net.bytebuddy.dynamic.DynamicType;
import net.bytebuddy.implementation.bytecode.assign.Assigner;
import org.probe.PerturbationGate;
import org.probe.ProbeCatalog;

import static net.bytebuddy.matcher.ElementMatchers.*;

public class ArgumentPerturbationStrategy implements PerturbationStrategy {

    @Override
    public DynamicType.Builder<?> apply(DynamicType.Builder<?> builder) {
        return builder.visit(
                Advice.to(ArgumentAdvice.class).on(
                        (isMethod().or(isConstructor()))
                                .and(not(isAbstract()))
                                .and(not(isNative()))
                )
        );
    }

    public static Object[] perturbArguments(Object[] args, String locationKey) {
        if (args == null || args.length == 0) return args;

        Object[] modifiedArgs = null;

        for (int i = 0; i < args.length; i++) {
            Object currentArg = args[i];
            if (currentArg == null) continue;

            String argKey = locationKey + ":arg:" + i;
            int probeId = ProbeCatalog.idForLocation(argKey);

            if (probeId != -1) {
                if (modifiedArgs == null) {
                    modifiedArgs = new Object[args.length];
                    System.arraycopy(args, 0, modifiedArgs, 0, args.length);
                }

                if (currentArg instanceof Integer num) {
                    modifiedArgs[i] = PerturbationGate.apply(num.intValue(), probeId);
                } else if (currentArg instanceof Boolean bool) {
                    modifiedArgs[i] = PerturbationGate.apply(bool.booleanValue(), probeId);
                } else {
                    modifiedArgs[i] = PerturbationGate.apply(currentArg, probeId);
                }
            }
        }

        return modifiedArgs != null ? modifiedArgs : args;
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