sub Main()
    check(SubtitleIndicatorLabel(invalid) = "Subtitles: Checking availability", "Missing older-server metadata is safe")
    check(SubtitleIndicatorLabel({count:0,state:"quota_wait"}) = "Subtitles: Not available yet · Download queued", "Queue is not advertised as ready")
    check(SubtitleIndicatorLabel({count:1,has_full:false}) = "Subtitles: Forced only (selected dialogue)", "Forced captions are labeled accurately")
    check(SubtitleIndicatorLabel({count:1,has_full:true,languages:["eng"],state:"quota_wait"}) = "Subtitles: Available · English", "Ready tracks take precedence over pending downloads")
    mixed = SubtitleSummaryFromTracks({state:"ready",tracks:[{language:"eng",kind:"forced"},{language:"spa",kind:"sdh"}]})
    check(SubtitleIndicatorLabel(mixed) = "Subtitles: Available · Spanish · SDH", "Full Spanish is not advertised as full English")
    check(SubtitleIndicatorLabel({episode_total:40,episodes_available:10,episodes_full:8},true) = "Subtitles: Full tracks on 8 of 40 episodes", "Partial show coverage is explicit")
    check(SubtitleIndicatorLabel({episode_total:3,episodes_available:3,episodes_full:3},true) = "Subtitles: All 3 episodes", "Complete show coverage")
    check(SubtitleIndicatorLabel({episode_total:3,episodes_available:1,episodes_full:0},true) = "Subtitles: Forced only on 1 of 3 episodes", "Forced-only show coverage")
    print "PASS: Subtitle availability labels"
end sub
sub check(condition as boolean, message as string)
    if not condition
        print "FAIL: "; message
        stop
    end if
end sub
