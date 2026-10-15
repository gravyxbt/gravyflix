sub initializeHistory()
    m.historyTask = invalid
    m.historyDirty = false
    m.historySessionId = ""
    m.historyClock = CreateObject("roTimespan")
    m.historyPosition = 0
    m.historyDuration = 0
    m.video.ObserveField("position", "onHistoryPosition")
    m.top.FindNode("restart").ObserveField("buttonSelected", "onRestart")
end sub

sub onRestart()
    m.launchIntent = "restart"
    onPlay()
end sub

sub beginHistory(plan as object)
    m.resumePending = 0
    if plan.resume_position <> invalid then m.resumePending = plan.resume_position
    m.historyPosition = 0
    m.historyDuration = 0
    if m.selected.duration <> invalid then m.historyDuration = m.selected.duration
    m.historyClock.Mark()
    if plan.session_id = invalid then return
    m.historyTask = CreateObject("roSGNode", "HistoryTask")
    m.historyTask.baseUrl = ServerUrl()
    m.historySessionId = plan.session_id
    m.historyTask.sessionId = plan.session_id
    m.historyTask.movieId = m.selected.id
    m.historyTask.ObserveField("saved", "onHistorySaved")
    m.historyTask.control = "RUN"
end sub

sub onHistoryPosition()
    if m.mode <> "video" then return
    previous = m.historyPosition
    m.historyPosition = m.video.position
    if m.video.duration > 0 then m.historyDuration = m.video.duration
    if m.historyClock.TotalSeconds() >= 15 or Abs(m.historyPosition - previous) > 8
        reportHistoryState(m.video.state)
    end if
end sub

sub historyState(state as string)
    if state = "playing" and m.resumePending <> invalid and m.resumePending > 0
        m.video.seek = m.resumePending
        m.historyPosition = m.resumePending
        m.resumePending = 0
    end if
    if state = "playing" or state = "paused" or state = "buffering"
        if m.video.duration > 0 then m.historyDuration = m.video.duration
        reportHistoryState(state)
    else if state = "finished" or state = "stopped" or state = "error"
        endHistory(state)
    end if
end sub

sub reportHistoryState(state as string)
    if m.historyTask = invalid then return
    if state <> "playing" and state <> "paused" and state <> "buffering" then return
    m.historyTask.snapshot = {position:m.historyPosition,duration:m.historyDuration,state:state}
    m.historyClock.Mark()
end sub

sub endHistory(state as string)
    if m.historyTask = invalid then return
    m.historyTask.snapshot = {position:m.historyPosition,duration:m.historyDuration,state:state}
    m.historyTask = invalid
end sub

sub onHistorySaved(event as object)
    saved = event.GetData()
    m.historyDirty = true
    if m.mode = "details" and m.selected <> invalid
        if saved.movie_id = m.selected.id and saved.completed = true and saved.session_id = m.historySessionId
            m.selected.completed = true
            m.selected.resume_position = 0
            m.play.text = "Play"
            m.top.FindNode("restart").visible = false
        end if
    end if
    if m.mode = "library" and not m.loading
        m.historyDirty = false
        loadMovies(false, true)
    end if
end sub
