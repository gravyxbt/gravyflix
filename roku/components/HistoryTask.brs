sub init()
    m.top.functionName = "reportHistory"
end sub

sub reportHistory()
    port = CreateObject("roMessagePort")
    m.top.ObserveField("snapshot", port)
    sequence = 0
    pending = m.top.snapshot
    lastState = ""
    clock = CreateObject("roTimespan")
    retryAt = 0
    terminalAt = 0
    while true
        event = Wait(500, port)
        if Type(event) = "roSGNodeEvent" then pending = m.top.snapshot
        if pending <> invalid and clock.TotalSeconds() >= retryAt
            sequence++
            payload = {sequence:sequence,position:pending.position,duration:pending.duration,state:pending.state}
            lastState = pending.state
            terminal = lastState = "finished" or lastState = "stopped" or lastState = "error" or lastState = "next" or lastState = "cancelled"
            if terminal and terminalAt = 0 then terminalAt = clock.TotalSeconds() + 30
            result = requestJson("/api/playback/sessions/" + m.top.sessionId + "/progress", "POST", FormatJson(payload), true, 3000)
            if result.error = invalid
                pending = invalid
                if terminal
                    m.top.saved = {movie_id:m.top.movieId,session_id:m.top.sessionId,completed:result.completed}
                    return
                end if
            else
                print "HISTORY: update deferred: "; result.error
                retryAt = clock.TotalSeconds() + 3
            end if
        end if
        if terminalAt > 0 and clock.TotalSeconds() >= terminalAt then return
        if m.top.cancelled then return
    end while
end sub
