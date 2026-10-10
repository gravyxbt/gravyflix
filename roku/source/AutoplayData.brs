' Pure recommendation policy; uses the existing catalog and playback identities.
function AutoplayId(item as object) as string
    if item.id = invalid then return ""
    return item.id.ToStr()
end function

function AutoplayNeedsConfirmation(transitions as integer) as boolean
    return transitions >= 3
end function

function AutoplayLabel(item as object) as string
    if item.kind = "episode" then return item.show_title + " · " + item.title
    return item.title
end function

function NextAutoplayItem(current as object, library as object, visited as object) as dynamic
    if current = invalid then return invalid
    currentId = AutoplayId(current)
    if current.kind = "episode"
        if current.season_number = invalid or current.episode_number = invalid then return invalid
        if current.season_number <= 0 then return invalid ' Extras and specials do not chain into seasons.
        lastEpisode = current.episode_number
        if current.episode_end <> invalid then lastEpisode = current.episode_end
        nextItem = invalid
        nextOrder = 10000000
        for each show in library
            if show.kind = "show" and show.seasons <> invalid
                for each season in show.seasons
                    for each episode in season.episodes
                        if episode.show_key = current.show_key and episode.season_number > 0
                            later = episode.season_number > current.season_number
                            if episode.season_number = current.season_number then later = episode.episode_number > lastEpisode
                            order = episode.season_number * 10000 + episode.episode_number
                            if later and order < nextOrder and not visited.DoesExist(AutoplayId(episode))
                                nextItem = episode
                                nextOrder = order
                            end if
                        end if
                    end for
                end for
            end if
        end for
        return nextItem
    end if
    ' Recommend only actual movies with known overlapping genres, not short test/bumper/sample clips.
    if current.genres = invalid then return invalid
    wanted = {}
    for each genre in current.genres
        wanted[LCase(genre)] = true
    end for
    best = invalid
    bestScore = 0
    bestTitle = ""
    for each item in library
        if item.kind <> "show" and item.kind <> "episode" and item.genres <> invalid
            id = AutoplayId(item)
            duration = 0
            if item.duration <> invalid then duration = item.duration
            if id <> currentId and not visited.DoesExist(id) and duration >= 600
                score = 0
                seen = {}
                for each genre in item.genres
                    name = LCase(genre)
                    if wanted.DoesExist(name) and not seen.DoesExist(name) then score++
                    seen[name] = true
                end for
                title = LCase(item.title)
                if score > bestScore or (score > 0 and score = bestScore and title < bestTitle)
                    best = item
                    bestScore = score
                    bestTitle = title
                end if
            end if
        end if
    end for
    return best
end function

' Movies use a reviewed/chapter credit marker; episodes keep their final-30-second window.
function MovieNextWindow(item as dynamic, duration as float, position as float) as boolean
    if duration <= 0 then return false
    if item <> invalid
        if item.kind = "movie" and item.credits_start <> invalid
            start = item.credits_start
            if start > 0 and start < duration then return position >= start
        end if
    end if
    return duration - position <= 30
end function
