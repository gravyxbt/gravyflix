
' Resolve household progress to a physical movie/episode, never a synthetic show ID.
function HomeResumeTarget(item as dynamic) as dynamic
    if item = invalid then return invalid
    target = item
    if item.kind = "show"
        target = item.resume_episode
        if target = invalid then return invalid
        if target.season_number = invalid or target.season_number <= 0 then return invalid
    end if
    if target.id = invalid or target.completed = true then return invalid
    if item.kind = "show" and item.continue_watching = true then return target
    if target.resume_position = invalid or target.resume_position <= 15 then return invalid
    if target.duration <> invalid
        if target.resume_position >= target.duration - 30 then return invalid
    end if
    return target
end function

function HomeActionLabel(item as dynamic) as string
    target = HomeResumeTarget(item)
    if target <> invalid
        if item.kind = "show" and target.resume_position = 0 then return "▶  Next Episode"
        return "▶  Resume"
    end if
    if item <> invalid
        if item.kind = "show" then return "Episodes"
    end if
    return "▶  Play"
end function
