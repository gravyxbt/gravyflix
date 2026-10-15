sub Main()
    m.mode = "library"
    m.loading = true
    m.historyDirty = false
    m.historySessionId = "current"
    event = {GetData:completedResult}
    onHistorySaved(event)
    check(m.historyDirty, "A save during an in-flight browse queues another refresh")
    check(m.requested = invalid, "In-flight browse is not replaced")
    m.loading = false
    onHistorySaved(event)
    check(not m.historyDirty and m.requested, "Acknowledged history refreshes cached shelves")
    m.mode = "details"
    m.selected = {id:9,resume_position:800,completed:false}
    m.play = {text:"Resume"}
    m.restart = {visible:true}
    m.top = {FindNode:getRestart,restart:m.restart}
    onHistorySaved(event)
    check(m.selected.completed and m.selected.resume_position = 0 and m.play.text = "Play", "Finished title no longer offers Resume")
    m.historySessionId = "newer-replay"
    m.selected.completed = false
    m.play.text = "Resume"
    onHistorySaved(event)
    check(not m.selected.completed and m.play.text = "Resume", "Late older-session acknowledgement cannot complete a replay")
    print "PASS: History save acknowledgements"
end sub
function completedResult() as object
    return {movie_id:9,completed:true,session_id:"current"}
end function
function getRestart(id as string) as object
    return m.restart
end function
sub loadMovies(rescan as boolean, preserve as boolean)
    m.requested = preserve
end sub
sub check(condition as boolean, message as string)
    if not condition then print "FAIL: "; message : stop
end sub
