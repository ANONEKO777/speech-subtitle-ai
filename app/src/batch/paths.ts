const VIDEO = /\.(mp4|mkv|mov|avi|webm|m4v|flv|wmv|ts|mpg|mpeg|mp3|wav|m4a|flac|ogg|aac|opus|3gp|mts|m2ts|ogv|wma|aiff|aif)$/i;

/** A dropped path with a media extension is a file. Any other is offered to the backend as a folder, which says if it is not one. */
export const classifyPath = (path: string): "file" | "folder" => (VIDEO.test(path) ? "file" : "folder");

export const baseName = (path: string): string => path.slice(Math.max(path.lastIndexOf("\\"), path.lastIndexOf("/")) + 1);
