// The lesson on a TVO learning-activity page is the one iframe with this id. Other embeds are widgets, and
// course pages show many lesson previews with other ids, so those pages have no single lesson.
const LESSON_FRAME_ID = 'la_iframe';

/** The value of an attribute in one opening tag, or null if the tag does not have it. */
function attributeOf(tag, name) {
    const match = tag.match(new RegExp(`\\s${name}\\s*=\\s*(?:"([^"]*)"|'([^']*)')`, 'i'));
    return match ? (match[1] ?? match[2]) : null;
}

/**
 * The path of the lesson's frame inside a captured page, such as "frames/f0.html". It is null when the
 * page has no lesson frame (a course or collection page) or the lesson could not be copied.
 *
 * @param {string} pageHtml the captured page's index.html
 * @returns {string | null}
 */
export function findLessonFrame(pageHtml) {
    for (const [tag] of pageHtml.matchAll(/<iframe\b[^>]*>/gi)) {
        if (attributeOf(tag, 'id') !== LESSON_FRAME_ID) continue;
        const src = attributeOf(tag, 'src');
        // Only a frame the capture copied next to the page can be shown; anything else points elsewhere.
        return src && /^frames\/f\d+\.html$/.test(src) ? src : null;
    }
    return null;
}
