import assert from 'node:assert/strict';
import { test } from 'node:test';
import { findLessonFrame } from './lessonFrame.js';

test('finds the frame of a learning activity page', () => {
    const html = '<body><iframe class="iframe-container" id="la_iframe" src="frames/f0.html" title=" Learning Activity Content" data-cid="c315"></iframe></body>';

    assert.equal(findLessonFrame(html), 'frames/f0.html');
});

test('finds it whatever order the attributes are in', () => {
    const html = '<iframe src="frames/f2.html" id="la_iframe"></iframe>';

    assert.equal(findLessonFrame(html), 'frames/f2.html');
});

test('is null on a course page, where every lesson preview has its own id', () => {
    const html = '<iframe id="u1_l1_iframe" class="preview_iframe" src="frames/f0.html"></iframe><iframe id="u1_l2_iframe" src="frames/f1.html"></iframe>';

    assert.equal(findLessonFrame(html), null);
});

test('is null when the lesson was not copied next to the page', () => {
    assert.equal(findLessonFrame('<iframe id="la_iframe" src="https://elsewhere.test/lesson"></iframe>'), null);
    assert.equal(findLessonFrame('<iframe id="la_iframe"></iframe>'), null);
});

test('ignores other frames that come before the lesson', () => {
    const html = '<iframe id="video" src="frames/f1.html"></iframe><iframe id="la_iframe" src="frames/f0.html"></iframe>';

    assert.equal(findLessonFrame(html), 'frames/f0.html');
});

test('is null when the page has no frames', () => {
    assert.equal(findLessonFrame('<body><p>Text</p></body>'), null);
});
