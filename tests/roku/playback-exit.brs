sub Main()
    m.top = {FindNode:findNode}
    for each kind in ["movie","episode"]
        m.mode = "video"
        m.selected = {kind:kind}
        m.video = {control:"",visible:true,state:"playing"}
        m.nextUp = {visible:true}
        m.queuedAutoplay = {id:7}
        m.autoplayCancelled = false
        m.nextItem = {id:7}
        m.playbackTask = {cancelled:false,UnobserveField:recordUnobserve}
        task = m.playbackTask
        m.prefetchTask = {cancelled:false}
        speculative = m.prefetchTask
        m.details = {visible:false}
        m.play = {SetFocus:recordFocus}
        m.movieInfo = {}
        m.detailsInfo = "Title synopsis"
        m.historyEnded = false
        m.loading = true
        check(onKeyEvent("back",true), "Scene Back fallback exits playback")
        check(m.mode = "details" and m.details.visible and not m.video.visible, "Back returns to title details for " + kind)
        check(m.video.control = "stop" and m.historyEnded, "Playback stops and progress is recorded")
        check(m.autoplayCancelled and m.queuedAutoplay = invalid and not m.nextUp.visible, "Countdown and queued autoplay are cancelled")
        check(task.cancelled and speculative.cancelled and m.playbackTask = invalid and m.prefetchTask = invalid, "Preparation tasks are released")
        check(m.play.focused, "Title page receives remote focus")
        m.video.state = "finished"
        onVideoState()
        check(m.mode = "details", "Late finished event cannot reopen autoplay")
    end for
    m.mode = "transition"
    m.queuedAutoplay = {id:8}
    exitPlayback()
    check(m.mode = "details" and m.queuedAutoplay = invalid, "Exit cancels an autoplay handoff too")
    m.video.state = "stopped"
    onVideoState()
    check(m.mode = "details", "Late stopped event cannot launch the queued title")
    print "PASS: Playback exit and autoplay cancellation"
end sub
sub endHistory(state as string)
    if m.mode <> "details" then print "FAIL: stop race was not guarded" : stop
    m.historyEnded = true
end sub
sub historyState(state as string)
end sub
sub hideNextUp()
    m.nextUp.visible = false
end sub
sub stopNextEpisodePreparation()
    if m.prefetchTask <> invalid then m.prefetchTask.cancelled = true
    m.prefetchTask = invalid
end sub
function findNode(id as string) as object
    return {visible:false}
end function
sub recordFocus(flag as boolean)
    m.focused = flag
end sub
sub recordUnobserve(field as string)
end sub
sub check(condition as boolean, message as string)
    if not condition then print "FAIL: "; message : stop
end sub
