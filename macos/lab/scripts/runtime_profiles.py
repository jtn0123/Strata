"""Permanent profiles qualified by the recorded M5 comparisons."""
import argparse

BASE = ['flash', '--engine', 'm5-small-stack', '--m5-tuning', 'small-reduce',
        '--tensor-api', 'on', '--context', '4096', '--ubatch', '512',
        '--cache-type', 'f16', '--spec', 'draft-mtp',
        '--draft-model', 'mtp_shared_packed_q3', '--draft', '3',
        '--draft-placement', 'mixed', '--draft-threads', '8', '--draft-p-min', '0.0']
PROFILES = {
    'balanced': dict(arguments=BASE, description='Normal English chat and code generation.'),
    'code-edit': dict(arguments=BASE + ['--lookup-profile', 'code-edit'],
                     description='Edits to supplied code. Confirmed on one Python file; broader speed coverage is pending.'),
}


def lookup_command(command, args):
    """Bound lookup to the exact configuration tested with real MTP fallback."""
    if getattr(args, 'lookup_profile', 'off') == 'off':
        return command
    required = dict(model='flash', engine='m5-small-stack', m5_tuning='small-reduce',
                    tensor_api='on', context=4096, ubatch=512, cache_type='f16',
                    spec='draft-mtp', draft_model='mtp_shared_packed_q3', draft=3,
                    draft_placement='mixed', draft_threads=8, draft_p_min=0.0)
    if any(getattr(args, key, None) != value for key, value in required.items()):
        raise ValueError('Code-edit lookup requires the qualified code-edit profile')
    result = list(command)
    index = result.index('--spec-type') + 1
    if result[index] != 'draft-mtp':
        raise ValueError('Code-edit lookup requires MTP fallback')
    result[index] = 'ngram-mod,draft-mtp'
    return result + ['--spec-ngram-mod-n-match', '16',
                     '--spec-ngram-mod-n-min', '1', '--spec-ngram-mod-n-max', '3']


def main(argv=None):
    import run
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=PROFILES, default='balanced')
    parser.add_argument('--port', type=int, default=8095)
    parser.add_argument('--native-port', type=int, default=8096)
    args = parser.parse_args(argv)
    print(f"Strata {args.profile}: {PROFILES[args.profile]['description']}", flush=True)
    run.main(PROFILES[args.profile]['arguments'] +
             ['--port', str(args.port), '--native-port', str(args.native_port)])


if __name__ == '__main__':
    main()
